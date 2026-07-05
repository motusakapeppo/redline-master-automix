cmake_minimum_required(VERSION 3.22)

project(RedLineMaster VERSION 1.0.0)
add_compile_options(/FS)
set(CMAKE_POLICY_DEFAULT_CMP0141        NEW      CACHE STRING "" FORCE)
set(CMAKE_MSVC_DEBUG_INFORMATION_FORMAT Embedded CACHE STRING "" FORCE)

# Add JUCE
add_subdirectory(JUCE)

# Make sure JUCE_FORMATS is defined if not set
set(JUCE_FORMATS VST3 AU Standalone)

juce_add_plugin(RedLineMaster
    COMPANY_NAME "Motus"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD TRUE
    PLUGIN_MANUFACTURER_CODE MotS
    PLUGIN_CODE AtmX
    FORMATS ${JUCE_FORMATS}
    PRODUCT_NAME "RedLine Master"
)

# Compile options
target_compile_features(RedLineMaster PUBLIC cxx_std_20)
target_compile_options(RedLineMaster_Standalone PRIVATE /FS)

# Add JuceHeader generation
juce_generate_juce_header(RedLineMaster)

target_sources(RedLineMaster PRIVATE
    src/PluginProcessor.cpp
    src/PluginEditor.cpp
    src/AnalyzerThread.cpp
)

target_include_directories(RedLineMaster PRIVATE src
    ${CMAKE_CURRENT_BINARY_DIR}/RedLineMaster_artefacts/JuceLibraryCode
)

target_link_libraries(RedLineMaster PRIVATE
    juce::juce_audio_utils
    juce::juce_dsp
    juce::juce_opengl
    juce::juce_gui_extra
    juce::juce_recommended_config_flags
    juce::juce_recommended_lto_flags
    juce::juce_recommended_warning_flags
)

target_link_libraries(RedLineMaster_Standalone PRIVATE
    juce::juce_dsp
    juce::juce_opengl
)