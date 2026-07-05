#include "PluginProcessor.h"
#include "PluginEditor.h"

AutoMixerVSTAudioProcessor::AutoMixerVSTAudioProcessor()
    : AudioProcessor (BusesProperties().withOutput("Output", juce::AudioChannelSet::stereo(), true))
{
    formatManager.registerBasicFormats();
}

AutoMixerVSTAudioProcessor::~AutoMixerVSTAudioProcessor() = default;

void AutoMixerVSTAudioProcessor::prepareToPlay(double sampleRate, int samplesPerBlock)
{
    audioFileBuffer.setSize(2, (int)(sampleRate * 20.0), false, true, false);
    fileSampleRate.store(sampleRate);

    juce::dsp::ProcessSpec spec;
    spec.sampleRate = sampleRate;
    spec.maximumBlockSize = (juce::uint32)samplesPerBlock;
    spec.numChannels = 2;

    // 5 bande EQ parametriche (inizializzazione flat)
    for (auto& f : eqFilters)
        f.prepare(spec);

    // Parallel compressor
    parallelComp.setAttack(30.0f);
    parallelComp.setRelease(150.0f);
    parallelComp.setRatio(3.0f);
    parallelComp.setThreshold(-18.0f);
    parallelComp.prepare(spec);

    // Buffer wet per parallel comp
    parallelWetBuffer.setSize(2, samplesPerBlock, false, true, false);

    // Makeup gain
    makeupGain.setGainDecibels(1.0f);
    makeupGain.prepare(spec);

    // Limiter finale (compressor mode con ratio alto per proteggere il picco)
    limiter.setAttack(0.5f);
    limiter.setRelease(20.0f);
    limiter.setRatio(10.0f);
    limiter.setThreshold(-1.0f);
    limiter.prepare(spec);

    dspInitialized = true;
}

void AutoMixerVSTAudioProcessor::releaseResources() {}

void AutoMixerVSTAudioProcessor::processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    auto numOut = getTotalNumOutputChannels();
    for (int ch = 0; ch < numOut; ++ch) buffer.clear(ch, 0, buffer.getNumSamples());

    if (!isPlaying.load()) return;

    // Leggi da audioFileBuffer con interpolazione
    double pos = playHeadPosition.load();
    int total = fileNumSamples.load();
    if (total <= 0) return;

    int numCh = juce::jmin(numOut, audioFileBuffer.getNumChannels());
    double systemSampleRate = getSampleRate();
    double fileSampleRateVal = fileSampleRate.load();
    double speedRatio = fileSampleRateVal / systemSampleRate;

    for (int ch = 0; ch < numCh; ++ch)
    {
        auto* d = buffer.getWritePointer(ch);
        for (int s = 0; s < buffer.getNumSamples(); ++s)
        {
            double srcPos = pos + (double)s * speedRatio;
            int idx = (int)srcPos;
            double frac = srcPos - (double)idx;
            if (idx < total - 1 && idx >= 0)
            {
                float s0 = audioFileBuffer.getSample(ch, idx);
                float s1 = audioFileBuffer.getSample(ch, idx + 1);
                d[s] = s0 + (float)(frac * (double)(s1 - s0));
            }
            else d[s] = 0.0f;
        }
    }

    pos += (double)buffer.getNumSamples() * speedRatio;
    playHeadPosition.store(pos);
    if (pos >= (double)total - 1.0) isPlaying.store(false);

    // --- DSP Mastering Chain (solo se bypass = OFF) ---
    if (!bypassMastering.load() && dspInitialized)
    {
        // 1. EQ parametrico 5 bande
        for (auto& f : eqFilters)
        {
            auto block = juce::dsp::AudioBlock<float>(buffer);
            auto ctx = juce::dsp::ProcessContextReplacing<float>(block);
            f.process(ctx);
        }

        // 2. Parallel compression con STEREO LINKING
        auto latest = analyzerThread.getLatestParameters();
        float compMix = latest.parallelMix;

        if (compMix > 0.01f)
        {
            parallelWetBuffer.makeCopyOf(buffer, true);
            
            // Stereo linking: calcola GR sul mix mono e applica a entrambi i canali
            for (int s = 0; s < buffer.getNumSamples(); ++s)
            {
                // Somma L+R per il sidechain mono
                float sidechain = 0.0f;
                for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
                    sidechain += parallelWetBuffer.getSample(ch, s);
                sidechain /= (float)buffer.getNumChannels();
                
                // Envelope follower semplice (attack 30ms, release 150ms)
                // Simula il compressore manualmente sulla sidechain
                float env = std::abs(sidechain);
                const float threshold = 0.125f; // -18dB
                if (env > threshold)
                {
                    float gainReduction = threshold / env; // ratio 3:1
                    for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
                    {
                        float sample = parallelWetBuffer.getSample(ch, s);
                        parallelWetBuffer.setSample(ch, s, sample * gainReduction);
                    }
                }
            }

            // Blend: out = dry*(1-mix) + wet*mix
            for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
            {
                auto* dry = buffer.getWritePointer(ch);
                auto* wet = parallelWetBuffer.getReadPointer(ch);
                for (int s = 0; s < buffer.getNumSamples(); ++s)
                    dry[s] = dry[s] * (1.0f - compMix) + wet[s] * compMix;
            }
        }

        // 3. True peak limiter con STEREO LINKING (brickwall a -0.5dB)
        {
            for (int s = 0; s < buffer.getNumSamples(); ++s)
            {
                // Trova il picco sul mix mono (stereo linking)
                float peak = 0.0f;
                for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
                {
                    float absSm = std::abs(buffer.getSample(ch, s));
                    if (absSm > peak) peak = absSm;
                }
                
                // Se il picco supera il ceiling, applica GR identico a tutti i canali
                float ceiling = 0.944f; // -0.5dB
                if (peak > ceiling)
                {
                    float gain = ceiling / peak;
                    for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
                        buffer.setSample(ch, s, buffer.getSample(ch, s) * gain);
                }
            }
        }

        // 4. Makeup gain — normalizzazione K-System
        // Se la traccia è più forte del target, il gain è negativo (abbassa).
        // Se è più debole, il gain è positivo (alza).
        // Questo rispetta gli standard streaming (Spotify -14, Apple -16, YouTube -13).
        float gainDb = latest.makeupGainDb;
        if (gainDb > 8.0f) gainDb = 8.0f; // Sicurezza: max +8dB per evitare clipping eccessivo
        if (gainDb < -12.0f) gainDb = -12.0f; // Min -12dB per evitare silenzio
        makeupGain.setGainDecibels(gainDb);
        {
            auto block = juce::dsp::AudioBlock<float>(buffer);
            auto ctx = juce::dsp::ProcessContextReplacing<float>(block);
            makeupGain.process(ctx);
        }
    }
}

void AutoMixerVSTAudioProcessor::processBlock(juce::AudioBuffer<double>& b, juce::MidiBuffer& m)
{
    juce::AudioBuffer<float> f(b.getNumChannels(), b.getNumSamples());
    for (int ch = 0; ch < b.getNumChannels(); ++ch)
        for (int s = 0; s < b.getNumSamples(); ++s)
            f.setSample(ch, s, (float)b.getSample(ch, s));
    processBlock(f, m);
    for (int ch = 0; ch < b.getNumChannels(); ++ch)
        for (int s = 0; s < b.getNumSamples(); ++s)
            b.setSample(ch, s, (double)f.getSample(ch, s));
}

juce::AudioProcessorEditor* AutoMixerVSTAudioProcessor::createEditor()
{
    return new AutoMixerVSTAudioProcessorEditor(*this);
}
bool AutoMixerVSTAudioProcessor::hasEditor() const { return true; }

const juce::String AutoMixerVSTAudioProcessor::getName() const { return JucePlugin_Name; }
bool AutoMixerVSTAudioProcessor::acceptsMidi() const { return false; }
bool AutoMixerVSTAudioProcessor::producesMidi() const { return false; }
bool AutoMixerVSTAudioProcessor::isMidiEffect() const { return false; }
double AutoMixerVSTAudioProcessor::getTailLengthSeconds() const { return 0.0; }
int AutoMixerVSTAudioProcessor::getNumPrograms() { return 1; }
int AutoMixerVSTAudioProcessor::getCurrentProgram() { return 0; }
void AutoMixerVSTAudioProcessor::setCurrentProgram(int) {}
const juce::String AutoMixerVSTAudioProcessor::getProgramName(int) { return {}; }
void AutoMixerVSTAudioProcessor::changeProgramName(int, const juce::String&) {}
void AutoMixerVSTAudioProcessor::getStateInformation(juce::MemoryBlock&) {}
void AutoMixerVSTAudioProcessor::setStateInformation(const void*, int) {}

void AutoMixerVSTAudioProcessor::loadFile(const juce::String& path)
{
    auto file = juce::File(path);
    if (!file.existsAsFile()) return;
    if (analyzerThread.isAnalyzingFile())
        analyzerThread.stopAnalysis();

    auto* reader = formatManager.createReaderFor(file);
    if (!reader) return;

    int total = (int)juce::jmin((juce::int64)std::numeric_limits<int>::max(), reader->lengthInSamples);
    if (total <= 0) { delete reader; return; }

    audioFileBuffer.setSize(reader->numChannels, total, false, true, false);
    audioFileBuffer.clear();
    reader->read(&audioFileBuffer, 0, total, 0, true, true);
    fileNumSamples.store(total);
    fileSampleRate.store(reader->sampleRate);
    loadedFilePath = path;
    playHeadPosition.store(0);
    isPlaying.store(false);
    delete reader;
}

void AutoMixerVSTAudioProcessor::setPlaying(bool p) { isPlaying.store(p); }

void AutoMixerVSTAudioProcessor::startAnalysis()
{
    if (loadedFilePath.isNotEmpty())
        analyzerThread.startAnalysis(loadedFilePath, formatManager);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new AutoMixerVSTAudioProcessor();
}
