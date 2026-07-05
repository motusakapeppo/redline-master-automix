#pragma once
#include <JuceHeader.h>
#include <juce_dsp/juce_dsp.h>
#include <atomic>
#include "RuleEngine.h"

struct EngineParameters {
    juce::String detectedGenre = "Pop/Rock Standard";
    float targetLufs = -11.0f;
    float smartAttackTime = 10.0f;
    float smartReleaseTime = 150.0f;
    float smartRatio = 3.0f;
    float eqMudGainDB = 0.0f;
    float eqPresenceGainDB = 0.0f;
    float eqAirGainDB = 0.0f;
    float smartThreshold = -18.0f;
    float makeupGainDb = 0.0f;
    float parallelMix = 0.25f;
    float limiterCeilingDb = -0.5f;
    float limiterMaxGRDb = 3.0f;
    juce::String description;
    
    // EQ bands (5 bande parametriche)
    float eqBandFreq[5] = { 80.0f, 250.0f, 1000.0f, 3000.0f, 10000.0f };
    float eqBandGainDb[5] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };
    float eqBandQ[5] = { 0.7f, 1.0f, 1.0f, 1.0f, 0.7f };
    int eqBandType[5] = { 1, 0, 0, 0, 2 }; // LowShelf, Peak, Peak, Peak, HighShelf
    
    // Spectral analysis results
    float spectralBalance[6] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };
    float spectralTilt = 0.0f;
    
    // Stem separation results (from Demucs)
    float vocalProminenceDb = 0.0f;
    float bassLoudnessDb = 0.0f;
    float drumsLoudnessDb = 0.0f;
    bool isVocalLow = false;
    bool isBassLow = false;
    bool isDrumsLow = false;
    bool stemAnalysisComplete = false;
};

class AnalyzerThread : public juce::Thread, public juce::ChangeBroadcaster
{
public:
    AnalyzerThread();
    ~AnalyzerThread() override;

    void startAnalysis(const juce::String& path, juce::AudioFormatManager& fmtMgr);
    void stopAnalysis();

    float getProgress() const { return progress.load(); }
    bool isAnalyzingFile() const { return isAnalyzing.load(); }
    bool isAnalysisCompleted() const { return analysisCompleted.load(); }
    EngineParameters getLatestParameters() const { return latestParams; }
    juce::String getStatusMessage() const { return statusMsg; }

private:
    void run() override;
    void analyzeFileInternal(const juce::String& path, juce::AudioFormatManager& fmtMgr);
    void runSourceSeparation(const juce::String& path);
    void parseStemJson(const juce::String& jsonPath);

    std::atomic<bool> isAnalyzing { false };
    std::atomic<float> progress { 0.0f };
    std::atomic<bool> analysisCompleted { false };
    EngineParameters latestParams;
    juce::String statusMsg;
    juce::CriticalSection statusLock;

    // Dati per il thread
    juce::String currentFilePath;
    juce::AudioFormatManager* formatManagerPtr = nullptr;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AnalyzerThread)
};
