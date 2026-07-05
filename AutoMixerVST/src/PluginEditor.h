#pragma once
#include <JuceHeader.h>
#include "PluginProcessor.h"

class AutoMixerVSTAudioProcessorEditor : public juce::AudioProcessorEditor,
                                         public juce::Timer,
                                         public juce::FileDragAndDropTarget
{
public:
    AutoMixerVSTAudioProcessorEditor(AutoMixerVSTAudioProcessor&);
    ~AutoMixerVSTAudioProcessorEditor() override;

    void paint(juce::Graphics&) override;
    void resized() override;
    void timerCallback() override;

    bool isInterestedInFileDrag(const juce::StringArray&) override;
    void filesDropped(const juce::StringArray&, int, int) override;

private:
    AutoMixerVSTAudioProcessor& audioProcessor;
    juce::String loadedFileName;
    EngineParameters latestParams;
    bool analysisDone = false;

    //--- Pulsanti ---
    juce::TextButton loadButton{ "1. Carica Brano" };
    juce::TextButton analyzeButton{ "2. Avvia Analisi" };
    juce::TextButton playButton{ "Play" };
    juce::TextButton stopButton{ "Stop" };
    juce::TextButton bypassButton{ "Bypass" };
    bool bypassActive = false;

    //--- Informazioni ---
    juce::Label fileLabel;
    juce::Label statusLabel;
    juce::Label genreLabel;
    juce::Label lufsLabel;
    juce::Label compressLabel;
    juce::Label eqLabel;
    juce::Label descLabel;
    juce::Label progressLabel;
    juce::ProgressBar progressBar{ progressValue };
    double progressValue = 0.0;

    std::unique_ptr<juce::FileChooser> fileChooser;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AutoMixerVSTAudioProcessorEditor)
};
