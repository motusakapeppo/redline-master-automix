#include "PluginProcessor.h"
#include "PluginEditor.h"

AutoMixerVSTAudioProcessorEditor::AutoMixerVSTAudioProcessorEditor(AutoMixerVSTAudioProcessor& p)
    : AudioProcessorEditor(&p), audioProcessor(p)
{
    setSize(520, 420);
    startTimerHz(20);

    auto setLabelStyle = [](juce::Label& lbl, const juce::Colour& col, float size) {
        lbl.setColour(juce::Label::textColourId, col);
        lbl.setFont(juce::FontOptions(size, juce::Font::bold));
        lbl.setJustificationType(juce::Justification::centredLeft);
    };
    auto addLabel = [this](juce::Label& lbl) { addAndMakeVisible(lbl); };

    // Stili label
    setLabelStyle(fileLabel, juce::Colour::fromString("#FF003F"), 14.0f);
    setLabelStyle(statusLabel, juce::Colours::grey, 12.0f);
    setLabelStyle(genreLabel, juce::Colours::lightgrey, 13.0f);
    setLabelStyle(lufsLabel, juce::Colours::lightgrey, 13.0f);
    setLabelStyle(compressLabel, juce::Colours::lightgrey, 13.0f);
    setLabelStyle(eqLabel, juce::Colours::lightgrey, 13.0f);
    setLabelStyle(descLabel, juce::Colour::fromString("#AAAAAA"), 11.0f);
    setLabelStyle(progressLabel, juce::Colours::grey, 11.0f);

    addLabel(fileLabel);
    addLabel(statusLabel);
    addLabel(genreLabel);
    addLabel(lufsLabel);
    addLabel(compressLabel);
    addLabel(eqLabel);
    addLabel(descLabel);
    addLabel(progressLabel);

    // Progress bar
    progressBar.setColour(juce::ProgressBar::backgroundColourId, juce::Colour::fromString("#222222"));
    progressBar.setColour(juce::ProgressBar::foregroundColourId, juce::Colour::fromString("#FF003F"));
    addAndMakeVisible(progressBar);

    // Pulsanti
    addAndMakeVisible(loadButton);
    loadButton.onClick = [this] {
        fileChooser = std::make_unique<juce::FileChooser>("Scegli un audio...",
            juce::File::getSpecialLocation(juce::File::userDesktopDirectory),
            "*.wav;*.mp3;*.aif;*.aiff;*.flac");
        fileChooser->launchAsync(juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles,
            [this](const juce::FileChooser& fc) {
                auto f = fc.getResult();
                if (f != juce::File{}) {
                    audioProcessor.loadFile(f.getFullPathName());
                    loadedFileName = f.getFileName();
                    fileLabel.setText("File: " + f.getFileName(), juce::dontSendNotification);
                    analyzeButton.setEnabled(true);
                    analysisDone = false;
                    fileLabel.setColour(juce::Label::textColourId, juce::Colour::fromString("#44CC66"));
                }
            });
    };

    addAndMakeVisible(analyzeButton);
    analyzeButton.onClick = [this] {
        audioProcessor.startAnalysis();
        analyzeButton.setEnabled(false);
        progressLabel.setText("Analisi in corso...", juce::dontSendNotification);
    };
    analyzeButton.setEnabled(false);

    addAndMakeVisible(playButton);
    playButton.onClick = [this] {
        if (audioProcessor.fileNumSamples.load() > 0) {
            bool playing = audioProcessor.isPlaying.load();
            audioProcessor.setPlaying(!playing);
            statusLabel.setText(playing ? "In pausa" : "Riproduzione in corso...", juce::dontSendNotification);
        }
    };
    playButton.setEnabled(false);

    addAndMakeVisible(stopButton);
    stopButton.onClick = [this] {
        audioProcessor.isPlaying.store(false);
        audioProcessor.playHeadPosition.store(0.0);
        statusLabel.setText("Fermo", juce::dontSendNotification);
    };
    stopButton.setEnabled(false);

    addAndMakeVisible(bypassButton);
    bypassButton.setClickingTogglesState(true);
    bypassButton.onClick = [this] {
        bool isDown = bypassButton.getToggleState();
        audioProcessor.bypassMastering.store(isDown);
        if (isDown)
            statusLabel.setText("Bypass ON — audio originale", juce::dontSendNotification);
        else
            statusLabel.setText("Mastering attivo", juce::dontSendNotification);
    };
    bypassButton.setEnabled(false);

    statusLabel.setText("Carica un file audio per iniziare", juce::dontSendNotification);

    // Nascondi i risultati all'avvio
    genreLabel.setVisible(false);
    lufsLabel.setVisible(false);
    compressLabel.setVisible(false);
    eqLabel.setVisible(false);
    descLabel.setVisible(false);
}

AutoMixerVSTAudioProcessorEditor::~AutoMixerVSTAudioProcessorEditor() = default;

void AutoMixerVSTAudioProcessorEditor::paint(juce::Graphics& g)
{
    // Sfondo scuro
    g.fillAll(juce::Colour::fromString("#0A0A0A"));

    // Bordo sottile
    g.setColour(juce::Colour::fromString("#FF003F").withAlpha(0.2f));
    g.drawRect(getLocalBounds(), 1);
}

void AutoMixerVSTAudioProcessorEditor::resized()
{
    auto r = getLocalBounds().reduced(16);

    auto topArea = r.removeFromTop(40);
    loadButton.setBounds(topArea.removeFromLeft(140).reduced(2));
    analyzeButton.setBounds(topArea.removeFromLeft(140).reduced(2));

    r.removeFromTop(8);

    // File info
    fileLabel.setBounds(r.removeFromTop(22));

    // Progress
    progressLabel.setBounds(r.removeFromTop(20));
    r.removeFromTop(2);
    progressBar.setBounds(r.removeFromTop(18));

    r.removeFromTop(6);

    // Risultati mastering (dopo analisi)
    genreLabel.setBounds(r.removeFromTop(20));
    lufsLabel.setBounds(r.removeFromTop(20));
    compressLabel.setBounds(r.removeFromTop(20));
    eqLabel.setBounds(r.removeFromTop(20));
    descLabel.setBounds(r.removeFromTop(36));

    r.removeFromTop(6);

    // Riproduzione
    auto transportArea = r.removeFromTop(30);
    playButton.setBounds(transportArea.removeFromLeft(60).reduced(2));
    stopButton.setBounds(transportArea.removeFromLeft(60).reduced(2));
    bypassButton.setBounds(transportArea.removeFromLeft(90).reduced(2));
    statusLabel.setBounds(transportArea);

    // Risultati mastering
    auto resultsArea = r.removeFromTop(120);
    int labelH = 20;
    genreLabel.setBounds(resultsArea.removeFromTop(labelH));
    lufsLabel.setBounds(resultsArea.removeFromTop(labelH));
    compressLabel.setBounds(resultsArea.removeFromTop(labelH));
    eqLabel.setBounds(resultsArea.removeFromTop(labelH));
    descLabel.setBounds(resultsArea.removeFromTop(36));
}

void AutoMixerVSTAudioProcessorEditor::timerCallback()
{
    if (audioProcessor.isAnalysisRunning()) {
        float p = audioProcessor.getAnalysisProgress();
        progressValue = (double)p;
        progressLabel.setText("Analisi: " + juce::String((int)(p * 100)) + "%", juce::dontSendNotification);

        // Mostra progress
        genreLabel.setVisible(false);
        lufsLabel.setVisible(false);
        compressLabel.setVisible(false);
        eqLabel.setVisible(false);
        descLabel.setVisible(false);
    } else if (!analysisDone && audioProcessor.isAnalysisCompleted()) {
        // Analisi completata — mostra i risultati
        analysisDone = true;
        latestParams = audioProcessor.getLatestAnalysis();
        progressLabel.setText("Analisi completata!", juce::dontSendNotification);
        progressValue = 1.0;

        genreLabel.setText("Genere rilevato: " + latestParams.detectedGenre, juce::dontSendNotification);
        lufsLabel.setText("LUFS: " + juce::String(latestParams.targetLufs, 1) + "  |  Makeup Gain: " + juce::String(latestParams.makeupGainDb, 1) + " dB", juce::dontSendNotification);
        compressLabel.setText("Compressione: Attack " + juce::String((int)latestParams.smartAttackTime) + "ms  Release " + juce::String((int)latestParams.smartReleaseTime) + "ms  Ratio " + juce::String(latestParams.smartRatio, 1) + ":1", juce::dontSendNotification);
        eqLabel.setText("EQ: Mud " + juce::String(latestParams.eqMudGainDB, 1) + "dB  Presence " + juce::String(latestParams.eqPresenceGainDB, 1) + "dB  Air " + juce::String(latestParams.eqAirGainDB, 1) + "dB", juce::dontSendNotification);
        descLabel.setText(latestParams.description, juce::dontSendNotification);

        genreLabel.setVisible(true);
        lufsLabel.setVisible(true);
        compressLabel.setVisible(true);
        eqLabel.setVisible(true);
        descLabel.setVisible(true);

        playButton.setEnabled(true);
        stopButton.setEnabled(true);
        bypassButton.setEnabled(true);
        analyzeButton.setEnabled(true);
        analyzeButton.setButtonText("2. Rianalizza");
    }

    if (audioProcessor.isPlaying.load()) {
        double pos = audioProcessor.playHeadPosition.load();
        double len = audioProcessor.fileNumSamples.load();
        if (len > 0)
            statusLabel.setText("Riproduco... " + juce::String((int)(pos / len * 100)) + "%", juce::dontSendNotification);
    }
}

bool AutoMixerVSTAudioProcessorEditor::isInterestedInFileDrag(const juce::StringArray&) { return true; }
void AutoMixerVSTAudioProcessorEditor::filesDropped(const juce::StringArray& files, int, int)
{
    if (files.size() > 0) {
        audioProcessor.loadFile(files[0]);
        loadedFileName = files[0];
        fileLabel.setText("File: " + juce::File(files[0]).getFileName(), juce::dontSendNotification);
        analyzeButton.setEnabled(true);
        fileLabel.setColour(juce::Label::textColourId, juce::Colour::fromString("#44CC66"));
    }
}
