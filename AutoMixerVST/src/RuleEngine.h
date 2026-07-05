#pragma once
#include <JuceHeader.h>
#include <array>
#include <cmath>

struct EQBand {
    float freq;
    float gainDb;
    float q;
    int type; // 0=Peak, 1=LowShelf, 2=HighShelf
};

class RuleEngine {
public:
    static constexpr int NUM_EQ_BANDS = 5;
    
    struct RuleContext {
        float lufs;
        float crest;      // Raw crest factor (peak/rms)
        float crestK;     // K-weighted crest factor
        float subBassRatio;
    };
    
    struct Result {
        float attackMs = 10.0f;
        float releaseMs = 150.0f;
        float ratio = 3.0f;
        float thresholdDb = -18.0f;
        std::array<EQBand, NUM_EQ_BANDS> eqBands;
        float makeupGainDb = 0.0f;
        float limiterCeilingDb = -0.5f;
        float limiterMaxGRDb = 3.0f;
        float parallelMix = 0.25f;
        juce::String genre = "Pop/Rock";
        juce::String description;
    };
    
    struct GenreProfile {
        const char* name;
        std::array<EQBand, NUM_EQ_BANDS> bands;
        float attackMs;
        float releaseMs;
        float ratio;
        float thresholdDb;
        float parallelMix;
    };
    
    Result evaluate(const RuleContext& ctx) const {
        Result r;
        
        //--- K-System: gamma dinamica → headroom (Katz) ---
        float dynamicRangeDb = 20.0f * std::log10(ctx.crestK + 1e-6f);
        float headroomTarget;
        
        if (dynamicRangeDb > 14.0f) {
            headroomTarget = -20.0f; // K-20: materiale dinamico (classica, jazz)
        } else if (dynamicRangeDb > 10.0f) {
            headroomTarget = -14.0f; // K-14: pop, rock
        } else {
            headroomTarget = -12.0f; // K-12: materiale già compresso (EDM, radio)
        }
        
        //--- Genre detection (Stavrou/Eargle + K-System) ---
        const GenreProfile* profile = nullptr;
        
        if (ctx.crest < 10.0f && ctx.subBassRatio > 0.3f) {
            // EDM / Urban: bass-heavy, low crest
            static const GenreProfile edmProf = {
                "EDM / Urban",
                {{
                    { 60.0f,  3.0f, 0.7f, 1 },  // LowShelf 60Hz +3dB (sub thump)
                    { 250.0f, -2.5f, 1.2f, 0 },  // Peak 250Hz -2.5dB (mud cut)
                    { 800.0f, -1.0f, 1.0f, 0 },  // Peak 800Hz -1dB (boxiness cut)
                    { 3000.0f, 2.0f, 1.0f, 0 },  // Peak 3kHz +2dB (presence)
                    { 10000.0f, 1.0f, 0.7f, 2 }, // HighShelf 10kHz +1dB (air/snap)
                }},
                3.0f, 80.0f, 5.0f, -22.0f, 0.20f
            };
            profile = &edmProf;
        }
        else if (ctx.crest < 12.0f && ctx.subBassRatio > 0.2f) {
            // Pop / Rock: balanced
            static const GenreProfile popProf = {
                "Pop / Rock",
                {{
                    { 80.0f,  1.0f, 0.7f, 1 },  // LowShelf 80Hz +1dB
                    { 250.0f, -2.0f, 1.2f, 0 },  // Peak 250Hz -2dB (mud cut)
                    { 1000.0f, 0.0f, 1.0f, 0 },  // Flat a 1kHz
                    { 3000.0f, 3.0f, 1.0f, 0 },  // Peak 3kHz +3dB (presenza)
                    { 10000.0f, 2.0f, 0.7f, 2 }, // HighShelf 10kHz +2dB (air)
                }},
                8.0f, 120.0f, 3.5f, -18.0f, 0.30f
            };
            profile = &popProf;
        }
        else if (ctx.crest > 14.0f && ctx.subBassRatio < 0.15f) {
            // Acoustic / Classical
            static const GenreProfile acouProf = {
                "Acoustic / Classical",
                {{
                    { 60.0f,  0.0f, 0.7f, 1 },  // No sub boost
                    { 250.0f, -0.5f, 1.2f, 0 },  // Leggero mud cut
                    { 1000.0f, 0.0f, 1.0f, 0 },  // Flat medi
                    { 3000.0f, 1.0f, 0.8f, 0 },  // Leggera presenza
                    { 10000.0f, 3.0f, 0.7f, 2 }, // HighShelf +3dB (aria strumenti acustici)
                }},
                20.0f, 300.0f, 2.0f, -16.0f, 0.15f
            };
            profile = &acouProf;
        }
        else if (ctx.crest > 12.0f && ctx.subBassRatio > 0.2f) {
            // Jazz / Vintage
            static const GenreProfile jazzProf = {
                "Jazz / Vintage",
                {{
                    { 40.0f,  0.5f, 0.7f, 1 },  // LowShelf 40Hz +0.5dB (warmth)
                    { 250.0f, -0.5f, 1.0f, 0 },  // Leggero mud cut
                    { 800.0f, -0.5f, 1.0f, 0 },  // Boxiness cut leggero
                    { 3000.0f, 1.5f, 0.8f, 0 },  // Presence
                    { 10000.0f, 0.5f, 0.7f, 2 }, // Leggero air
                }},
                12.0f, 200.0f, 2.5f, -18.0f, 0.25f
            };
            profile = &jazzProf;
        }
        else if (ctx.crest < 13.0f && ctx.subBassRatio > 0.35f) {
            // Hip-Hop: sub pesante, presenza vocale
            static const GenreProfile hiphopProf = {
                "Hip-Hop",
                {{
                    { 50.0f,  4.0f, 0.7f, 1 },  // LowShelf 50Hz +4dB (sub)
                    { 250.0f, -2.5f, 1.2f, 0 },  // Mud cut
                    { 800.0f, -1.5f, 1.0f, 0 },  // Boxiness cut
                    { 2000.0f, 2.0f, 0.8f, 0 },  // Presenza vocale (non 3kHz)
                    { 10000.0f, 0.0f, 0.7f, 2 }, // Flat alti
                }},
                5.0f, 100.0f, 4.0f, -20.0f, 0.20f
            };
            profile = &hiphopProf;
        }
        else {
            // Default / Balanced
            static const GenreProfile defProf = {
                "Balanced",
                {{
                    { 80.0f,  0.5f, 0.7f, 1 },
                    { 250.0f, -1.0f, 1.0f, 0 },
                    { 1000.0f, 0.0f, 1.0f, 0 },
                    { 3000.0f, 1.5f, 1.0f, 0 },
                    { 10000.0f, 1.0f, 0.7f, 2 },
                }},
                10.0f, 150.0f, 3.0f, -18.0f, 0.25f
            };
            profile = &defProf;
        }
        
        if (profile) {
            r.genre = profile->name;
            r.eqBands = profile->bands;
            r.attackMs = profile->attackMs;
            r.releaseMs = profile->releaseMs;
            r.ratio = profile->ratio;
            r.thresholdDb = profile->thresholdDb;
            r.parallelMix = profile->parallelMix;
        }
        
        //--- K-System: makeup gain basato su headroom (Katz) ---
        // Quanto gain serve per portare il materiale al target K?
        float targetLufs = headroomTarget + 4.0f; // K-20 → -16 LUFS target, K-14 → -10 LUFS target
        r.makeupGainDb = targetLufs - ctx.lufs;
        
        //--- Descrizione ---
        r.description = profile ? profile->name : "Balanced";
        r.description += "  K-";
        r.description += (headroomTarget == -20.0f) ? "20" : (headroomTarget == -14.0f) ? "14" : "12";
        r.description += "  Gain " + juce::String(r.makeupGainDb, 1) + "dB";
        r.description += "  Glue " + juce::String((int)r.attackMs) + "/" + juce::String((int)r.releaseMs) + "ms";
        
        return r;
    }
};
