'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';

type Log = {
    ts: string;
    cam: string;
    type: string;
    conf: number;
    score: number;
    severity: string;
    note: string;
};

type Snapshot = {
    ts: string;
    cam: string;
    type: string;
    severity: string;
    dataUrl: string;
};

type Camera = {
    id: string;
    name: string;
};

const cameras: Camera[] = [
    { id: "CAM-1", name: "ATM Lobby" },
    { id: "CAM-2", name: "ATM Exterior" },
    { id: "CAM-3", name: "Side Entrance" },
    { id: "CAM-4", name: "Parking View" },
];

export default function Home() {
    /* State */
    const [role, setRole] = useState("GUARD");
    const [selectedCam, setSelectedCam] = useState("CAM-1");
    const [riskScore, setRiskScore] = useState(0);
    const [gateLocked, setGateLocked] = useState(false);
    const [detectionReasons, setDetectionReasons] = useState<string[]>([]);
    const [logs, setLogs] = useState<Log[]>([]);
    const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
    const [networkStatus, setNetworkStatus] = useState("ONLINE");
    const [hwConnected, setHwConnected] = useState(false); // Hardware Status
    const [remoteStatus, setRemoteStatus] = useState("Standby");
    const [ackText, setAckText] = useState("");
    const [ackLog, setAckLog] = useState("No acknowledgement yet.");
    const [isConnected, setIsConnected] = useState(false);
    const [camSearch, setCamSearch] = useState("");
    const [sirenPlaying, setSirenPlaying] = useState(false);
    const [audioBlocked, setAudioBlocked] = useState(false);

    /* Toggles */
    const [soundEnabled, setSoundEnabled] = useState(true);
    const [autoLockEnabled, setAutoLockEnabled] = useState(true);

    /* Refs */
    const imgRef = useRef<HTMLImageElement>(null);
    const videoWsRef = useRef<WebSocket | null>(null);
    const sirenAudioRef = useRef<HTMLAudioElement | null>(null);

    /* Helper Functions */
    const nowStr = () => new Date().toLocaleString();
    const timeOnly = () => new Date().toLocaleTimeString();
    const clamp = (n: number, a: number, b: number) => Math.max(a, Math.min(b, n));

    const severityFromScore = (score: number) => {
        if (score >= 75) return "high";
        if (score >= 40) return "med";
        return "low";
    };

    const riskTextFromScore = (score: number) => {
        if (score >= 75) return "HIGH";
        if (score >= 40) return "MEDIUM";
        return "LOW";
    };

    const riskFillColor = (score: number) => {
        if (score >= 75) return "rgba(239,68,68,0.85)";
        if (score >= 40) return "rgba(245,158,11,0.90)";
        return "rgba(16,185,129,0.85)";
    };

    /* Actions */
    const playSiren = () => {
        // Debug: Text-to-Speech to verify audio system works
        const utterance = new SpeechSynthesisUtterance("Siren Activated. Warning.");
        utterance.rate = 1.2;
        window.speechSynthesis.speak(utterance);

        if (!soundEnabled) return;
        if (sirenAudioRef.current && sirenAudioRef.current.paused) {
            sirenAudioRef.current.play()
                .then(() => setAudioBlocked(false)) // Success
                .catch(e => {
                    console.error("Audio play failed (Autoplay prevented):", e);
                    setAudioBlocked(true); // Show unlock button
                });
            setSirenPlaying(true);
        }
    };

    const stopSiren = () => {
        if (sirenAudioRef.current) {
            sirenAudioRef.current.pause();
            sirenAudioRef.current.currentTime = 0;
            setSirenPlaying(false);
        }
        // Notify backend
        fetch('http://localhost:8000/control/siren', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: 'OFF' })
        }).catch(e => console.error(e));
    };

    const lockGate = () => {
        setGateLocked(true);
        setRemoteStatus("Gate Locked ✅");
        // playSiren() handled by backend status sync usually, but we can force it
    };

    const unlockGate = () => {
        if (role !== "ADMIN") return alert("Admin access required for unlock.");
        setGateLocked(false);
        setRemoteStatus("Unlocked ✅");
        stopSiren();
    };

    const sirenOn = () => {
        // if (role !== "ADMIN") return alert("Admin access required for siren.");
        setRemoteStatus("Siren Activated ✅");
        playSiren(); // Instant feedback
        fetch('http://localhost:8000/control/siren', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: 'ON' })
        }).catch(e => console.error(e));
    };

    /* Effects */
    useEffect(() => {
        sirenAudioRef.current = new Audio('/sounds/custom_siren.mp3');
        sirenAudioRef.current.loop = true;

        // Video WebSocket
        const videoWs = new WebSocket('ws://localhost:8000/ws/video');
        videoWsRef.current = videoWs;

        videoWs.onopen = () => setIsConnected(true);
        videoWs.onclose = () => setIsConnected(false);
        videoWs.onmessage = (event) => {
            const blob = event.data;
            if (imgRef.current) {
                const prevUrl = imgRef.current.src;
                const newUrl = URL.createObjectURL(blob);
                imgRef.current.src = newUrl;

                // CRITICAL FIX: Revoke old URL to prevent memory leak
                if (prevUrl && prevUrl.startsWith('blob:')) {
                    URL.revokeObjectURL(prevUrl);
                }
            }
        };

        // Status WebSocket
        const statusWs = new WebSocket('ws://localhost:8000/ws/status');
        statusWs.onmessage = (event) => {
            const data = JSON.parse(event.data);
            // console.log("WS Data:", data); // Debug
            const score = data.threat_score;
            setRiskScore(score);

            // update reasons
            if (data.reasons) {
                setDetectionReasons(data.reasons);
            }

            if (data.lock_status === 'LOCKED') setGateLocked(true);

            // Sync Siren
            if (data.siren && !sirenPlaying) {
                if (soundEnabled) playSiren();
            } else if (!data.siren && sirenPlaying) {
                stopSiren(); // Backend says off
            }
        };

        return () => {
            videoWs.close();
            statusWs.close();
            stopSiren();
        };
    }, [sirenPlaying, soundEnabled]);


    /* Computed Styles */
    const radarX = 30 + (riskScore * 0.5);
    const radarY = 20 + (Math.abs(50 - riskScore) * 0.35);
    const dotColor = riskScore >= 75 ? "rgba(239,68,68,0.95)" : riskScore >= 40 ? "rgba(245,158,11,0.95)" : "rgba(16,185,129,0.95)";
    const camDetails = cameras.find(c => c.id === selectedCam);

    return (
        <main className="layout">
            <header className="topbar" style={{ gridColumn: "1 / -1" }}>
                <div className="brand">
                    <img src="/images/nextgen-logo.png" alt="Logo" className="ngd-logo" />
                    <div className="brand-text">
                        <h1>ARGUS <span style={{ fontSize: '0.6em', color: hwConnected ? '#10B981' : '#EF4444', border: '1px solid currentColor', borderRadius: '4px', padding: '2px 6px', marginLeft: '10px' }}>
                            {hwConnected ? "ARDUINO ONLINE" : "ARDUINO OFF"}
                        </span></h1>
                        <p>AI-powered Robbery Guard & Unified Surveillance</p>
                    </div>
                </div>
                <div className="top-right">
                    <div className="chips">
                        <div className="chip">ATM-ID: <b id="atmId">ATM-01</b></div>
                        <div className="chip">Location: <b id="atmLoc">Prayagraj</b></div>
                        <div className="chip">Role: <b>{role}</b></div>
                    </div>
                    <div className="statusRow">
                        <div className={`pill net ${networkStatus.toLowerCase()}`}>{networkStatus}</div>
                        <div className={`pill ${riskScore >= 75 ? 'crit' : riskScore >= 40 ? 'warn' : 'safe'}`}>
                            {riskScore >= 75 ? 'CRITICAL' : riskScore >= 40 ? 'WARNING' : 'SAFE'}
                        </div>
                    </div>
                </div>
            </header>

            <aside className="card sidebar">
                <div className="card-head">
                    <h2>Cameras</h2>
                    <span className="hint">Switch live feeds</span>
                </div>
                <div className="searchBox">
                    <input placeholder="Search camera…" value={camSearch} onChange={(e) => setCamSearch(e.target.value)} />
                </div>
                <div className="camList">
                    {cameras.filter(c => c.id.toLowerCase().includes(camSearch.toLowerCase()) || c.name.toLowerCase().includes(camSearch.toLowerCase())).map(c => (
                        <button
                            key={c.id}
                            className={`camBtn p-3 rounded-lg text-left transition-all ${selectedCam === c.id ? 'bg-indigo-600 border-l-4 border-cyan-400 shadow-[0_0_15px_rgba(99,102,241,0.5)]' : 'bg-slate-900/60 hover:bg-slate-800 border border-slate-700/50 hover:shadow-[0_0_10px_rgba(255,255,255,0.1)]'}`}
                            onClick={() => setSelectedCam(c.id)}
                            style={{ color: '#ffffff' }}
                        >
                            <div className="camTitle font-bold text-sm tracking-wide shadow-black drop-shadow-md" style={{ color: '#ffffff' }}>{c.id}</div>
                            <div className="camSub text-xs mt-0.5 font-light" style={{ color: '#cccccc' }}>{c.name}</div>
                        </button>
                    ))}
                </div>
                <div className="divider"></div>
                <div className="card-head">
                    <h2>User & Controls</h2>
                    <span className="hint">Access control</span>
                </div>
                <div className="roleBox">
                    <button className={`btn small ${role === 'GUARD' ? 'primary' : ''}`} onClick={() => setRole('GUARD')}>Guard View</button>
                    <button className={`btn small ${role === 'ADMIN' ? 'primary' : ''}`} onClick={() => setRole('ADMIN')}>Admin View</button>
                </div>
                <div className="toggleRow">
                    <label className="toggle">
                        <input type="checkbox" checked={soundEnabled} onChange={(e) => setSoundEnabled(e.target.checked)} />
                        <span className="slider"></span>
                    </label>
                    <div>
                        <div className="toggleTitle">Alert Sound</div>
                        <div className="toggleSub">Beep/Siren on CRITICAL</div>
                    </div>
                </div>
                <div className="toggleRow">
                    <label className="toggle">
                        <input type="checkbox" checked={autoLockEnabled} onChange={(e) => setAutoLockEnabled(e.target.checked)} />
                        <span className="slider"></span>
                    </label>
                    <div>
                        <div className="toggleTitle">Auto Gate Lock</div>
                        <div className="toggleSub">Lock when risk is high</div>
                    </div>
                </div>
            </aside>

            <section className={`card camera ${sirenPlaying ? 'flash' : ''}`} id="cameraCard">
                <div className="card-head">
                    <h2>Live Camera Feed</h2>
                    <span className="hint">Real-time monitoring</span>
                </div>
                <div className="videoBox">
                    <div className="videoTop">
                        <div className="camLabel">{camDetails?.id} • {camDetails?.name}</div>
                        {audioBlocked && (
                            <div
                                className="liveTag"
                                style={{ backgroundColor: '#DC2626', cursor: 'pointer', marginRight: '8px' }}
                                onClick={() => { playSiren(); }}
                            >
                                🔇 ENABLE AUDIO
                            </div>
                        )}
                        <div className="liveTag">LIVE</div>
                    </div>
                    <img
                        ref={imgRef}
                        alt="Live Feed"
                        className="w-full h-full object-contain absolute inset-0"
                        style={{ zIndex: 1 }}
                    />
                    {!isConnected && (
                        <div className="videoPlaceholder absolute inset-0 z-0">CCTV STREAM DISCONNECTED</div>
                    )}
                    {sirenPlaying && (
                        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-10">
                            <div className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></div>
                            <div className="bg-red-600 text-white px-6 py-2 rounded-full font-bold shadow-xl animate-pulse">SIREN ACTIVE</div>
                        </div>
                    )}
                </div>

                {/* Advanced Capabilities Widget */}
                {/* Advanced Capabilities Widget */}
                <div className="grid grid-cols-2 gap-4 mt-4">
                    {/* Capabilities Module */}
                    <div className="relative p-4 rounded-xl border border-cyan-900/30 bg-black/40 backdrop-blur-sm overflow-hidden">
                        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-50"></div>
                        <h3 className="text-[10px] tracking-[0.2em] font-bold text-cyan-400 uppercase mb-3 flex items-center gap-2">
                            <span className="w-2 h-2 bg-cyan-500 rounded-full animate-pulse"></span>
                            Active Protocols
                        </h3>
                        <ul className="space-y-2 text-xs text-slate-300 font-mono">
                            <li className="flex items-center gap-2">
                                <span className="text-cyan-600">»</span>
                                <span>WEAPON_DETECTION_V2</span>
                                <span className="text-[10px] text-green-400 ml-auto">[ACTIVE]</span>
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-cyan-600">»</span>
                                <span>FACE_CONCEALMENT_SCAN</span>
                                <span className="text-[10px] text-green-400 ml-auto">[ACTIVE]</span>
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-cyan-600">»</span>
                                <span>CROWD_ANOMALY_TRACKER</span>
                                <span className="text-[10px] text-green-400 ml-auto">[ACTIVE]</span>
                            </li>
                        </ul>
                    </div>

                    {/* Threat Analysis Module */}
                    <div className={`relative p-4 rounded-xl border backdrop-blur-sm transition-all duration-300 ${riskScore > 60 ? 'border-red-500/50 bg-red-950/20 shadow-[0_0_15px_rgba(239,68,68,0.2)]' : 'border-slate-700/30 bg-black/40'}`}>
                        <h3 className={`text-[10px] tracking-[0.2em] font-bold uppercase mb-3 flex items-center gap-2 ${riskScore > 60 ? 'text-red-400' : 'text-slate-400'}`}>
                            <span className={`w-2 h-2 rounded-full ${riskScore > 60 ? 'bg-red-500 animate-ping' : 'bg-slate-600'}`}></span>
                            Target Analysis
                        </h3>

                        {riskScore > 60 ? (
                            <div className="font-mono">
                                <div className="text-red-400 font-bold text-sm mb-1 tracking-wide flex items-center gap-2">
                                    ⚠️ THREAT IDENTIFIED
                                </div>
                                <div className="w-full bg-red-900/30 h-1.5 rounded-full mt-2 mb-2 overflow-hidden">
                                    <div className="h-full bg-red-500 animate-[progress_1s_ease-in-out_infinite]" style={{ width: '90%' }}></div>
                                </div>
                                <div className="flex justify-between items-end">
                                    <div className="text-[10px] text-red-300">CONFIDENCE LEVEL</div>
                                    <div className="text-lg font-bold text-red-500">{(riskScore * 0.98).toFixed(1)}%</div>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex flex-col justify-center items-center text-slate-600 gap-2 min-h-[60px]">
                                <div className="w-8 h-8 rounded-full border-2 border-slate-800 border-t-cyan-500/50 animate-spin"></div>
                                <div className="text-[10px] tracking-widest uppercase">Scanning Area...</div>
                            </div>
                        )}
                    </div>
                </div>

            </section>

            <aside className="card rightPanel" style={{ opacity: role === "GUARD" ? 0.85 : 1, filter: role === "GUARD" ? "grayscale(0.1)" : "none" }}>
                <div className="card-head">
                    <h2>Risk Intelligence</h2>
                    <span className="hint">Score + patterns</span>
                </div>
                <div className="riskBlock">
                    <div className="riskTop">
                        <div>
                            <div className="smallLabel">RISK LEVEL</div>
                            <div className="riskValue" style={{ color: riskScore >= 75 ? '#fecaca' : riskScore >= 40 ? '#fde68a' : '#a7f3d0' }}>{riskTextFromScore(riskScore)}</div>
                        </div>
                        <div className="riskScoreBox">
                            <div className="smallLabel">SCORE</div>
                            <div className="score">{riskScore}</div>
                        </div>
                    </div>
                    <div className="riskBar">
                        <div className="fill" style={{ width: `${riskScore}%`, background: riskFillColor(riskScore) }}></div>
                    </div>
                </div>

                <div className="radarCard">
                    <div className="card-head compact">
                        <h2>Threat Heat Radar</h2>
                        <span className="hint">Visual indicator</span>
                    </div>
                    <div className="radar">
                        <div className="ring r1"></div>
                        <div className="ring r2"></div>
                        <div className="ring r3"></div>
                        <div className="sweep"></div>
                        <div className="dot" style={{ left: `${clamp(radarX, 15, 85)}%`, top: `${clamp(radarY, 15, 80)}%`, background: dotColor }}></div>
                    </div>
                </div>

                <div className="remoteCard">
                    <div className="card-head">
                        <h2>Remote Sensors / IoT</h2>
                        <span className="hint">IoT Actions ({gateLocked ? "LOCKED 🔒" : "UNLOCKED 🔓"})</span>
                    </div>
                    <div className="remoteBtns grid grid-cols-2 gap-2">
                        <button className="btn bg-rose-700 hover:bg-rose-600 text-white font-bold" onClick={() => lockGate()}>LOCK GATE</button>
                        <button className="btn bg-emerald-700 hover:bg-emerald-600 text-white font-bold" onClick={() => unlockGate()}>UNLOCK</button>
                        <button
                            className={`btn font-bold text-white transition-all ${sirenPlaying ? 'bg-amber-600 border border-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.6)] animate-pulse' : 'bg-amber-700 hover:bg-amber-600'}`}
                            onClick={() => sirenOn()}
                        >
                            {sirenPlaying ? 'SIREN ACTIVE 🔊' : 'SIREN ON 📢'}
                        </button>
                        <button className="btn bg-slate-700 hover:bg-slate-600 text-slate-300 font-bold" onClick={() => stopSiren()}>SILENCE 🔇</button>
                    </div>
                    <div className="remoteStatus" dangerouslySetInnerHTML={{ __html: `Remote Status: <b>${remoteStatus}</b>` }}></div>
                    <div className="divider"></div>
                    <div className="ackBox">
                        <div className="smallLabel">Alert Acknowledgement</div>
                        <input placeholder="Officer name..." value={ackText} onChange={(e) => setAckText(e.target.value)} />
                        <button className="btn primary" onClick={() => { setAckText(""); stopSiren(); }}>Acknowledge Alert</button>
                    </div>
                </div>

                <div className="panicCard" style={{ marginTop: '12px' }}>
                    <div className="card-head">
                        <h2>Emergency Override</h2>
                        <span className="hint">Manual lockdown</span>
                    </div>
                    <button className="btn panic" onClick={() => { setRiskScore(95); playSiren(); if (autoLockEnabled) lockGate(); }}>MANUAL EMERGENCY LOCKDOWN</button>
                </div>
            </aside>

            <section className="card bottomWide">
                <div className="bottomGrid">
                    <div className="panel">
                        <div className="card-head">
                            <h2>Live Detections</h2>
                            <span className="hint">Type + confidence</span>
                        </div>
                        <ul className="detList" style={{ maxHeight: '150px', overflowY: 'auto' }}>
                            {detectionReasons.length === 0 ? (
                                <li className="mutedItem">System scanning... Normal behavior.</li>
                            ) : (
                                detectionReasons.map((reason, idx) => (
                                    <li key={idx} className="flex items-center gap-2 text-sm text-red-300 py-1">
                                        <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                                        {reason}
                                    </li>
                                ))
                            )}
                        </ul>
                    </div>

                    <div className="panel">
                        <div className="card-head">
                            <h2>Threat Timeline</h2>
                            <span className="hint">Recent severity</span>
                        </div>
                        {/* Placeholder for timeline */}
                        <div className="timeline">
                            <div className="timelineEmpty">Real-time recording</div>
                        </div>
                    </div>

                    <div className="panel">
                        <div className="card-head">
                            <h2>About ARGUS</h2>
                            <span className="hint">Overview</span>
                        </div>
                        <div className="aboutBox">
                            <p><b>ARGUS</b> monitors camera feeds and detects threats like <b>weapons</b>, <b>masked faces</b>, and <b>crowd anomalies</b>.</p>
                            <div className="tags">
                                <span className="tag">Threat Detection</span>
                                <span className="tag">Auto Lock</span>
                                <span className="tag">Siren Active</span>
                            </div>
                            <div className="creditFooter">
                                <img src="/images/nextgen-logo.png" alt="NGD" />
                                <span>Designed by <b>Next Gen Developers</b></span>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
        </main>
    );
}
