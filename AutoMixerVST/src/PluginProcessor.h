#pragma once
#include <JuceHeader.h>
#include <juce_dsp/juce_dsp.h>
#include "AnalyzerThread.h"
#include <array>

class AutoMixerVSTAudioProcessor : public juce::AudioProcessor
{
public:
    AutoMixerVSTAudioProcessor();
    ~AutoMixerVSTAudioProcessor() override;

    void prepareToPlay(double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    void processBlock(juce::AudioBuffer<double>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override;

    const juce::String getName() const override;
    bool acceptsMidi() const override;
    bool producesMidi() const override;
    bool isMidiEffect() const override;
    double getTailLengthSeconds() const override;

    int getNumPrograms() override;
    int getCurrentProgram() override;
    void setCurrentProgram(int) override;
    const juce::String getProgramName(int) override;
    void changeProgramName(int, const juce::String&) override;

    void getStateInformation(juce::MemoryBlock&) override;
    void setStateInformation(const void*, int) override;

    // --- Pubblico per l'editor ---
    juce::AudioBuffer<float> audioFileBuffer;
    juce::AudioFormatManager formatManager;
    std::atomic<int> fileNumSamples { 0 };
    std::atomic<double> fileSampleRate { 44100.0 };
    std::atomic<double> playHeadPosition { 0.0 };
    std::atomic<bool> isPlaying { false };
    std::atomic<bool> bypassMastering { false };
    juce::String loadedFilePath;

    void loadFile(const juce::String& path);
    void setPlaying(bool p);
    void startAnalysis();
    EngineParameters getLatestAnalysis() const { return analyzerThread.getLatestParameters(); }
    float getAnalysisProgress() const { return analyzerThread.getProgress(); }
    bool isAnalysisRunning() const { return analyzerThread.isAnalyzingFile(); }
    bool isAnalysisCompleted() const { return analyzerThread.isAnalysisCompleted(); }
    juce::String getAnalysisStatus() const { return analyzerThread.getStatusMessage(); }

private:
    AnalyzerThread analyzerThread;

    //--- DSP Chain a 5 bande parametriche ---
    static constexpr int NUM_EQ_BANDS = 5;
    std::array<juce::dsp::IIR::Filter<float>, NUM_EQ_BANDS> eqFilters;
    juce::dsp::Compressor<float> parallelComp;
    juce::dsp::Gain<float> makeupGain;
    juce::AudioBuffer<float> parallelWetBuffer;
    bool dspInitialized = false;
    
    //--- True Peak Limiter (semplificato) ---
    juce::dsp::Compressor<float> limiter;
    float currentGR = 0.0f;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AutoMixerVSTAudioProcessor)
};
