#include "AnalyzerThread.h"
#include <cmath>

AnalyzerThread::AnalyzerThread() : juce::Thread("AnalyzerThread") {}
AnalyzerThread::~AnalyzerThread() { stopThread(1000); }

void AnalyzerThread::startAnalysis(const juce::String& path, juce::AudioFormatManager& fmtMgr)
{
    if (isAnalyzing.load()) return;

    analysisCompleted.store(false);
    statusMsg = {};
    currentFilePath = path;
    formatManagerPtr = &fmtMgr;
    progress.store(0.0f);
    isAnalyzing.store(true);
    startThread();
}

void AnalyzerThread::stopAnalysis()
{
    isAnalyzing.store(false);
}

void AnalyzerThread::run()
{
    analyzeFileInternal(currentFilePath, *formatManagerPtr);
    analysisCompleted.store(true);
    isAnalyzing.store(false);
    progress.store(1.0f);
    sendChangeMessage();
}

void AnalyzerThread::analyzeFileInternal(const juce::String& path, juce::AudioFormatManager& fmtMgr)
{
    auto file = juce::File(path);
    if (!file.existsAsFile()) {
        statusMsg = "File not found";
        return;
    }

    auto* reader = fmtMgr.createReaderFor(file);
    if (!reader) {
        statusMsg = "Unsupported format";
        return;
    }

    int totalSamples = (int)juce::jmin((juce::int64)std::numeric_limits<int>::max(), reader->lengthInSamples);
    if (totalSamples <= 0) { statusMsg = "Empty file"; delete reader; return; }

    double sampleRate = reader->sampleRate;
    delete reader; // Letto offline, non serve più il reader

    // Riapriamo il file per l'analisi K-Weighting (offline)
    auto* analysisReader = fmtMgr.createReaderFor(file);
    if (!analysisReader) { statusMsg = "Cannot reopen for analysis"; return; }

    int bufferSize = 8192;
    int numChannels = analysisReader->numChannels;

    // Filtri K-Weighting
    juce::dsp::ProcessSpec spec;
    spec.sampleRate = sampleRate;
    spec.maximumBlockSize = (juce::uint32)bufferSize;
    spec.numChannels = 1;

    juce::dsp::IIR::Filter<float> kShelf, kHPF;
    kShelf.coefficients = juce::dsp::IIR::Coefficients<float>::makeHighShelf(sampleRate, 1681.0f, 0.707f, juce::Decibels::decibelsToGain(4.0f));
    kHPF.coefficients = juce::dsp::IIR::Coefficients<float>::makeHighPass(sampleRate, 38.0f, 0.5f);
    kShelf.prepare(spec);
    kHPF.prepare(spec);

    juce::AudioBuffer<float> monoBuf(1, bufferSize);
    juce::AudioBuffer<float> monoMix(1, bufferSize);

    double sumSquares = 0.0;
    float peak = 0.0f;
    
    // Spectral analysis - 6 bandpass filters (fuori dal loop!)
    static constexpr int NUM_SPECTRAL_BANDS = 6;
    float spectralBandFreqs[NUM_SPECTRAL_BANDS] = { 40.0f, 100.0f, 400.0f, 1000.0f, 4000.0f, 10000.0f };
    float spectralBandEnergies[NUM_SPECTRAL_BANDS] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };
    juce::dsp::IIR::Filter<float> spectralFilters[NUM_SPECTRAL_BANDS];
    for (int b = 0; b < NUM_SPECTRAL_BANDS; ++b) {
        spectralFilters[b].coefficients = juce::dsp::IIR::Coefficients<float>::makeBandPass(sampleRate, spectralBandFreqs[b], 1.0f);
        spectralFilters[b].prepare(spec);
    }

    for (int i = 0; i < totalSamples; i += bufferSize)
    {
        if (!isAnalyzing.load()) break;

        int n = std::min(bufferSize, totalSamples - i);

        // Leggi e mixa a mono
        monoBuf.clear();
        for (int ch = 0; ch < numChannels; ++ch)
        {
            analysisReader->read(&monoMix, 0, n, i, true, ch);
            for (int s = 0; s < n; ++s)
                monoBuf.addSample(0, s, monoMix.getSample(0, s) / (float)numChannels);
        }

        // K-Weighting
        {
            auto block = juce::dsp::AudioBlock<float>(monoBuf.getArrayOfWritePointers(), 1, (size_t)n);
            auto ctx = juce::dsp::ProcessContextReplacing<float>(block);
            kShelf.process(ctx);
            kHPF.process(ctx);
        }

        // Accumula energia spettrale per ogni banda (raw, prima del K-Weighting)
        // Usiamo il buffer mono già letto prima del K-Weighting
        for (int b = 0; b < NUM_SPECTRAL_BANDS; ++b)
        {
            juce::AudioBuffer<float> bandBuf(1, n);
            bandBuf.copyFrom(0, 0, monoBuf.getReadPointer(0), n);
            auto block = juce::dsp::AudioBlock<float>(bandBuf.getArrayOfWritePointers(), 1, (size_t)n);
            auto ctx = juce::dsp::ProcessContextReplacing<float>(block);
            spectralFilters[b].process(ctx);
            for (int s = 0; s < n; ++s)
                spectralBandEnergies[b] += bandBuf.getSample(0, s) * bandBuf.getSample(0, s);
        }

    // Accumula
    auto* data = monoBuf.getReadPointer(0);
    for (int s = 0; s < n; ++s)
    {
        float sm = data[s];
        sumSquares += (double)(sm * sm);
        float a = std::abs(sm);
        if (a > peak) peak = a;
    }

    progress.store((float)i / (float)totalSamples);
}

delete analysisReader;

if (!isAnalyzing.load()) return;

// Calcola LUFS e parametri
double meanSq = sumSquares / (double)totalSamples;
float rms = std::sqrt((float)meanSq);
float crestK = (rms > 1e-6f) ? (peak / rms) : 1.0f;
float crest = crestK; // Per ora usiamo crestK come crest principale
float lufs = (meanSq > 1e-10) ? (float)(-0.691 + 10.0 * std::log10(meanSq)) : -144.0f;

// Calcola subBassRatio approssimato
float subBassRatio = 0.15f;

// Usa il RuleEngine per valutare le regole di mastering (Katz/Owsinski)
RuleEngine engine;
RuleEngine::RuleContext ctx;
ctx.lufs = lufs;
ctx.crest = crest;
ctx.crestK = crestK;
ctx.subBassRatio = subBassRatio;

auto result = engine.evaluate(ctx);

latestParams.detectedGenre = result.genre;
latestParams.targetLufs = lufs + result.makeupGainDb;
latestParams.smartAttackTime = result.attackMs;
latestParams.smartReleaseTime = result.releaseMs;
latestParams.smartRatio = result.ratio;
latestParams.smartThreshold = result.thresholdDb;
latestParams.makeupGainDb = result.makeupGainDb;
latestParams.description = result.description;
latestParams.parallelMix = result.parallelMix;
latestParams.limiterCeilingDb = result.limiterCeilingDb;
latestParams.limiterMaxGRDb = result.limiterMaxGRDb;

// Copia le bande EQ
for (int i = 0; i < RuleEngine::NUM_EQ_BANDS; ++i)
{
    latestParams.eqBandFreq[i] = result.eqBands[i].freq;
    latestParams.eqBandGainDb[i] = result.eqBands[i].gainDb;
    latestParams.eqBandQ[i] = result.eqBands[i].q;
    latestParams.eqBandType[i] = result.eqBands[i].type;
}

// Copia dati spettrali
float totalEnergy = 0.0f;
for (int b = 0; b < NUM_SPECTRAL_BANDS; ++b)
    totalEnergy += spectralBandEnergies[b];
if (totalEnergy > 1e-10f) {
    for (int b = 0; b < NUM_SPECTRAL_BANDS; ++b)
        latestParams.spectralBalance[b] = 10.0f * std::log10(spectralBandEnergies[b] / totalEnergy + 1e-10f);
}
latestParams.spectralTilt = (latestParams.spectralBalance[5] - latestParams.spectralBalance[0]);

statusMsg = "Analisi completata: " + result.genre + "  " + juce::String(lufs, 1) + " LUFS  " + result.description;
}

//==============================================================================
void AnalyzerThread::runSourceSeparation(const juce::String& path)
{
    auto file = juce::File(path);
    auto stemsDir = juce::File("D:\\FASE REM_automix\\AutoMixerVST\\stems");
    if (!stemsDir.exists())
        stemsDir.createDirectory();
    
    auto scriptPath = juce::File("D:\\FASE REM_automix\\AutoMixerVST\\scripts\\separate.py");
    if (!scriptPath.existsAsFile()) {
        statusMsg = "Script separator non trovato";
        return;
    }
    
    auto cmd = "python \"" + scriptPath.getFullPathName() + "\" \"" + path + "\" \"" + stemsDir.getFullPathName() + "\"";
    
    statusMsg = "Avvio separazione stems...";
    sendChangeMessage();
    
    juce::ChildProcess proc;
    if (!proc.start(cmd)) {
        statusMsg = "Errore avvio Demucs";
        return;
    }
    
    while (!proc.waitForProcessToFinish(1000))
    {
        if (!isAnalyzing.load()) {
            proc.kill();
            return;
        }
    }
    
    auto baseName = file.getFileNameWithoutExtension();
    auto jsonPath = stemsDir.getChildFile(baseName + "_stems.json");
    parseStemJson(jsonPath.getFullPathName());
}

void AnalyzerThread::parseStemJson(const juce::String& jsonPath)
{
    auto jsonFile = juce::File(jsonPath);
    if (!jsonFile.existsAsFile()) {
        statusMsg = "JSON stems non trovato";
        return;
    }
    
    auto jsonString = jsonFile.loadFileAsString();
    auto json = juce::JSON::parse(jsonString);
    
    auto* metricsObj = json["metrics"].getDynamicObject();
    if (metricsObj != nullptr) {
        auto& props = metricsObj->getProperties();
        
        auto getFloat = [&](const char* key, float def) -> float {
            return props.contains(key) ? (float)props[key] : def;
        };
        auto getBool = [&](const char* key, bool def) -> bool {
            return props.contains(key) ? (bool)props[key] : def;
        };
        
        latestParams.vocalProminenceDb = getFloat("vocal_prominence_db", 0.0f);
        latestParams.bassLoudnessDb = getFloat("bass_loudness_db", 0.0f);
        latestParams.drumsLoudnessDb = getFloat("drums_loudness_db", 0.0f);
        latestParams.isVocalLow = getBool("is_vocal_low", false);
        latestParams.isBassLow = getBool("is_bass_low", false);
        latestParams.isDrumsLow = getBool("is_drums_low", false);
        latestParams.stemAnalysisComplete = true;
        
        juce::String stemInfo;
        stemInfo += "Voce: " + juce::String(latestParams.vocalProminenceDb, 1) + "dB";
        stemInfo += " Basso: " + juce::String(latestParams.bassLoudnessDb, 1) + "dB";
        if (latestParams.isVocalLow) stemInfo += " [Vocale BASSA]";
        if (latestParams.isBassLow) stemInfo += " [Basso BASSO]";
        
        statusMsg = "Stems OK - " + stemInfo;
    } else {
        statusMsg = "JSON stems: formato non valido";
    }
    
    sendChangeMessage();
}
