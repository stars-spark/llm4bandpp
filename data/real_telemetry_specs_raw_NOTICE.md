# Documentation snapshots of the real telemetry sources

The field transcriptions in `data/real_telemetry_specs_v1/` (seven specifications) and `data/real_telemetry_specs_v2/` (12 client stacks) quote official
documentation and source code. The files below are the copies we read, retrieved with curl on 2 October 2026 (US Eastern time) and released
byte for byte under their own licenses. Each file keeps its copyright and license header; we did not modify any of them.

- **Retrieval time.** Files in `v1/raw` share one modification time, 2026-10-02T11:56Z; files in `v2/raw` were written between
  2026-10-03T03:13Z and 03:42Z (2 October in US Eastern time). The transcriptions record the date 2 October 2026.
- **URL.** *recorded*: the URL, with its commit when pinned, is cited in the transcription or its build script. *reconstructed*: the path is
  inferred from the file content and the recorded repository or site; the upstream check below confirms most of them.
- **Upstream check.** On 2026-10-11 we fetched each URL again and compared bytes: *identical*, *differs from the current upstream file*
  (the branch moved after retrieval), or *not checked* (the host answered with a bot-check page).
- **Derived text.** A `.txt` file next to an `.html` file of the same name is the page text extracted with `v1/raw/h2t.py` (BeautifulSoup
  `get_text`, scripts and styles removed); it carries the license of the page.
- **Our files.** `h2t.py`, `jitsi_commit_sha.txt`, `mediasoup_tree_sha.txt`, `pion_commit_sha.txt` and `chrome_commit.txt` were written by us
  (helper and provenance notes) and are released with the code.

License identifiers follow SPDX (https://spdx.org/licenses/). The GPL, LGPL, MPL and Apache files are documentation for the transcriptions;
no code in this package links to or includes them.

## Chromium webrtc-internals

License: BSD-3-Clause (Chromium; Copyright The Chromium Authors).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/chromium_stats_graph_helper.js` | `e6a87fd4d9cc9925b164d513d816db3e0e0f64736ae33d4e7f92fcdbc8649432` | https://github.com/chromium/chromium/blob/main/content/browser/webrtc/resources/stats_graph_helper.js | branch main, commit not recorded | identical |
| `v1/raw/chromium_stats_helper.js` | `df7e582841803d71c17eca908c53508fe0546188aa95b400dffb2204e99c2867` | https://github.com/chromium/chromium/blob/main/content/browser/webrtc/resources/stats_helper.js (reconstructed) | branch main, commit not recorded | identical |
| `v1/raw/chromium_stats_rates_calculator.js` | `f45e6c23e79bca6c7bba1e0e09a2f9663d16f967a320dc70a764d375fc8b0e0d` | https://github.com/chromium/chromium/blob/289a12e1f0beff39b6515449e10cb8f73e230d00/content/browser/webrtc/resources/stats_rates_calculator.js | commit 289a12e1f0beff39b6515449e10cb8f73e230d00 | identical |
| `v1/raw/chromium_webrtc_internals.js` | `01a768d439bb32716ff35f9fa52080db56bd2c0cb08801c2603563d5afcc29fc` | https://github.com/chromium/chromium/blob/main/content/browser/webrtc/resources/webrtc_internals.js (reconstructed) | branch main, commit not recorded | identical |

## GStreamer rtpmanager

License: LGPL-2.1-or-later (GStreamer; license header in the file).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/gst_gstrtpjitterbuffer.c` | `01d844a99ae0aee97cdba96330a604b20caa0a27adf0e00670e5a62c7ea24748` | https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/8d279edd98f4f6ffc08e6bc86516dfd01edf7210/subprojects/gst-plugins-good/gst/rtpmanager/gstrtpjitterbuffer.c | commit 8d279edd98f4f6ffc08e6bc86516dfd01edf7210 | not checked (host returned a bot-check page) |
| `v1/raw/gst_gstrtpsession.c` | `9dab1b1a98d22b883adc2665d672750421a943d46b959f21819a72c5dc3d1260` | https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/82a68b2f7919125f1f393f0846dea45bbe254b0d/subprojects/gst-plugins-good/gst/rtpmanager/gstrtpsession.c | commit 82a68b2f7919125f1f393f0846dea45bbe254b0d | not checked (host returned a bot-check page) |
| `v1/raw/gst_rtpsession.c` | `bb9535f31a08623a1562a926cebe09a20e94e23e21a94181c3a783e5e71a36bd` | https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/main/subprojects/gst-plugins-good/gst/rtpmanager/rtpsession.c (reconstructed) | branch main, commit not recorded | not checked (host returned a bot-check page) |
| `v1/raw/gst_rtpsource.c` | `559689a2851398d3a7701149e9396f394af6da82439a12b31002d256c39376dd` | https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/e27d76382a679c6f338b579e8f01a508ec9b551c/subprojects/gst-plugins-good/gst/rtpmanager/rtpsource.c | commit e27d76382a679c6f338b579e8f01a508ec9b551c | not checked (host returned a bot-check page) |
| `v1/raw/gst_rtpstats.c` | `662767a63236ec25bcd5f19dfeebdb73c6caabe5c5851c67dd6b795c0dc20676` | https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/5ff769d731e97fa05796f3ea32e039d267ad4f2f/subprojects/gst-plugins-good/gst/rtpmanager/rtpstats.c | commit 5ff769d731e97fa05796f3ea32e039d267ad4f2f | not checked (host returned a bot-check page) |
| `v1/raw/gst_rtpstats.h` | `3259ad29af4affcefea1a5e5b3a97154817855f845444c172159d69699eb324a` | https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/main/subprojects/gst-plugins-good/gst/rtpmanager/rtpstats.h (reconstructed) | branch main, commit not recorded | not checked (host returned a bot-check page) |
| `v1/raw/gst_rtptwcc.c` | `1f7d9ecd85d39faac780cef6a3d8a75566d63afe5f6d5f035c868cc13ed8455e` | https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/main/subprojects/gst-plugins-good/gst/rtpmanager/rtptwcc.c (reconstructed) | branch main, commit not recorded | not checked (host returned a bot-check page) |

## GStreamer rtpmanager documentation

License: LGPL-2.1-or-later (GStreamer documentation generated from the element sources).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/gstdoc_jb.html` | `3c41955cc497468c21ccabfa0b26a53d45fc031e496e1ec526276197e935ca7d` | https://gstreamer.freedesktop.org/documentation/rtpmanager/rtpjitterbuffer.html (reconstructed) | as served on the retrieval date | identical |
| `v1/raw/gstdoc_rtpsession.html` | `5aa63556f58f1744cd9370930dee794473f12645c752d4cef61758dc178a9933` | https://gstreamer.freedesktop.org/documentation/rtpmanager/rtpsession.html (reconstructed) | as served on the retrieval date | identical |
| `v1/raw/gstdoc_rtpsource.html` | `362a90f0c5deccd9951b673ef6671a8251c915dc4c3a73fab64c203bdb3b4058` | https://gstreamer.freedesktop.org/documentation/rtpmanager/RTPSource.html (reconstructed) | as served on the retrieval date | identical |

## Linux tcp_info

License: GPL-2.0 (Linux kernel; SPDX identifier in the file).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/inet_connection_sock.h` | `4a1585af7ff99790bd1cdfd5dbcdd36eeeecbdb902cf539bc9bec5d70de81b47` | https://github.com/torvalds/linux/blob/125755776bc6d4dd53eaf551c87e3d460625d638/include/net/inet_connection_sock.h (reconstructed) | commit not recorded; identical to the file at commit 125755776bc6d4dd53eaf551c87e3d460625d638 | identical |
| `v1/raw/ip-sysctl.rst` | `422b3a63c15c2eaf99a053062e46f1320bdab9c6d81a86835269828504ebd2f5` | https://github.com/torvalds/linux/blob/master/Documentation/networking/ip-sysctl.rst | branch master, commit not recorded | identical |
| `v1/raw/linux_linux_tcp.h` | `feb014e41e1f20fec35639fb4e41e4483dfd1ec05db7c869d3449cbf42ba55af` | https://github.com/torvalds/linux/blob/125755776bc6d4dd53eaf551c87e3d460625d638/include/linux/tcp.h (reconstructed) | commit not recorded; identical to the file at commit 125755776bc6d4dd53eaf551c87e3d460625d638 | identical |
| `v1/raw/linux_net_tcp.h` | `318474710a75e19f06deb9ce9b8af8fef4ed0fe3c7ba0d09837af2c4577a05c5` | https://github.com/torvalds/linux/blob/master/include/net/tcp.h (reconstructed) | branch master, commit not recorded (identical to master on 2026-10-11) | identical (to master) |
| `v1/raw/linux_sock.h` | `3669c26dc04a88bc5171e1aee82e1c2007181a5c565d6ccfb547641e792d70b6` | https://github.com/torvalds/linux/blob/master/include/net/sock.h (reconstructed) | branch master, commit not recorded (identical to master on 2026-10-11) | identical (to master) |
| `v1/raw/linux_tcp.c` | `926a440ea52322819bdbf74e5edc6704b9f26277a048cd848f1e960d21dbc2f5` | https://github.com/torvalds/linux/blob/125755776bc6d4dd53eaf551c87e3d460625d638/net/ipv4/tcp.c | commit 125755776bc6d4dd53eaf551c87e3d460625d638 | identical |
| `v1/raw/linux_tcp.h` | `6d981a5001fb09d406e1eb5046c1809743b9618e66d4d6f3360837986dc4c211` | https://github.com/torvalds/linux/blob/4fa4ac5e584841c0f9b01c2f7dd0c2e3caa8bca0/include/uapi/linux/tcp.h | commit 4fa4ac5e584841c0f9b01c2f7dd0c2e3caa8bca0 | identical |
| `v1/raw/linux_tcp_input.c` | `005afb8ca6617c1d51490e416b54a704b10f7ef0eef1b58ceccb3e28129ce0d8` | https://github.com/torvalds/linux/blob/master/net/ipv4/tcp_input.c (reconstructed) | branch master, commit not recorded (identical to master on 2026-10-11) | identical (to master) |

## iperf3

License: BSD-3-Clause (iperf3, Copyright The Regents of the University of California, LBNL; see the iperf LICENSE file).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/iperf_api.c` | `d1f72e1a7d01d664e036ea3fa41a11703f505ed3e338d1be6a6880a002774d0f` | https://github.com/esnet/iperf/blob/f9901828236c487fbe45807371866abeeb54a242/src/iperf_api.c | commit f9901828236c487fbe45807371866abeeb54a242 | identical |
| `v1/raw/iperf_udp.c` | `75ab0e1524d670b209e432d26af0bd60d0d3c22639fbf31a608bac31e02c9b23` | https://github.com/esnet/iperf/blob/f9901828236c487fbe45807371866abeeb54a242/src/iperf_udp.c | commit f9901828236c487fbe45807371866abeeb54a242 | identical |

## qlog main schema, draft-ietf-quic-qlog-main-schema-14

License: IETF Trust Legal Provisions (BCP 78); Internet-Draft copyright notice in the document.

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/qlog-main-14.txt` | `e1f1ed92bdcc62ed3ea25118bdc863c38bbff70974d8d714b2fa11c24f1a211b` | https://www.ietf.org/archive/id/draft-ietf-quic-qlog-main-schema-14.txt (reconstructed) | draft -14 | identical |

## qlog QUIC event definitions, draft-ietf-quic-qlog-quic-events-13

License: IETF Trust Legal Provisions (BCP 78); Internet-Draft copyright notice in the document.

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/qlog-quic-13.txt` | `9a5014a22223943cc435c6ff67eaf959538fd6697c3ef988477b1eebea64ac55` | https://www.ietf.org/archive/id/draft-ietf-quic-qlog-quic-events-13.txt (reconstructed) | draft -13 | identical |

## RFC 3550 (RTP)

License: IETF Trust Legal Provisions / RFC copyright statement in the document (Copyright The Internet Society 2003; may be copied in full).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/rfc3550.txt` | `4c210e9434b5b4c029e8536ad8991f3709bc3cbfa0999e951bcb4c2143c539e8` | https://www.rfc-editor.org/rfc/rfc3550.txt (reconstructed) | RFC 3550 (July 2003) | identical |

## RFC 3611 (RTCP XR)

License: IETF Trust Legal Provisions / RFC copyright statement in the document (Copyright The Internet Society 2003; may be copied in full).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/rfc3611.txt` | `a365d4b99a1993b43bd0cefa68ef1b57a27ec716c752e3361cef21415de89f2d` | https://www.rfc-editor.org/rfc/rfc3611.txt (reconstructed) | RFC 3611 (November 2003) | identical |

## iproute2 ss

License: GPL-2.0 (iproute2; SPDX identifier in ss.c).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/ss.8` | `e921d00ff66bda5291b8e1bddd7e31b429135dd8fab71d63b58764d2f32385bc` | https://git.kernel.org/pub/scm/network/iproute2/iproute2.git/tree/man/man8/ss.8 | branch main, commit not recorded | not checked (host returned a bot-check page) |
| `v1/raw/ss.c` | `c0b723ff31d2d2e631ce4f137822fc68aeb1fc2efc068d20da6c4b685e21c6d6` | https://git.kernel.org/pub/scm/network/iproute2/iproute2.git/tree/misc/ss.c | branch main, commit not recorded | not checked (host returned a bot-check page) |

## W3C WebRTC Statistics API, editor's draft (ReSpec source)

License: W3C Software and Document License (repository w3c/webrtc-stats).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/webrtc-stats-ed.html` | `0dad2db17cccdd6963ad9df56c646af09c554844749fb070e7dba5a09f69b968` | https://w3c.github.io/webrtc-stats/ (reconstructed) | editor's draft as served on the retrieval date | identical |

## W3C WebRTC Statistics API, editor's draft

License: W3C Software and Document License.

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/webrtc-stats-ed.txt` | `99e3a14caa96f0762dd453d6962c0099ef3e163c2e40ac20650404645ba246fc` | https://w3c.github.io/webrtc-stats/ (reconstructed) | text of webrtc-stats-ed.html | derived |

## W3C WebRTC Statistics API (Candidate Recommendation, TR version)

License: W3C Software and Document License (the page states: permissive document license rules apply).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/webrtc-stats.html` | `b899c5df0aabf3431027bafcbaae29cb6474dbd9c1f089377c69d0a4db8d67c8` | https://www.w3.org/TR/webrtc-stats/ | dated TR version as served on the retrieval date | identical |

## W3C WebRTC Statistics API

License: W3C Software and Document License (the page states: permissive document license rules apply).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v1/raw/webrtc-stats.txt` | `66c73104a220f1b6ccdc88fd5a81bf629ade84ccaddebc3900b395e1f1490a2e` | https://www.w3.org/TR/webrtc-stats/ | text of webrtc-stats.html | derived |

## WebRTC source (Chrome legacy getStats)

License: BSD-3-Clause (WebRTC; Copyright The WebRTC project authors).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/chrome_legacy_stats_collector.cc` | `469b028100e53d01b0ea64cb3a52472d6e33a47b71228f82ea2802fd0af93cb2` | https://webrtc.googlesource.com/src/+/538442a75d7ed04c962f288f9aedc21562d22e6d/pc/legacy_stats_collector.cc | commit 538442a75d7ed04c962f288f9aedc21562d22e6d | identical |
| `v2/raw/chrome_legacy_stats_types.cc` | `53ca951a0e3dbbadc9901c0944e2cf89df44cf4b61c2af94dc13e28d11ed6d94` | https://webrtc.googlesource.com/src/+/538442a75d7ed04c962f288f9aedc21562d22e6d/api/legacy_stats_types.cc (reconstructed) | commit 538442a75d7ed04c962f288f9aedc21562d22e6d | identical |
| `v2/raw/chrome_legacy_stats_types.h` | `ec60054ea2454a02857ec729995c7632789a1a4b2c543ec045f08ce59f725cd3` | https://webrtc.googlesource.com/src/+/538442a75d7ed04c962f288f9aedc21562d22e6d/api/legacy_stats_types.h (reconstructed) | commit 538442a75d7ed04c962f288f9aedc21562d22e6d | identical |
| `v2/raw/chrome_media_channel.h` | `1443a22df008f4b9a5fef46fa335ddf55e0ca0f64e5ea27cf3b8cbee75f0d18f` | https://webrtc.googlesource.com/src/+/538442a75d7ed04c962f288f9aedc21562d22e6d/media/base/media_channel.h (reconstructed) | commit 538442a75d7ed04c962f288f9aedc21562d22e6d | identical |
| `v2/raw/chrome_webrtc_video_engine.cc` | `fc21f0b6ebb285e164dde130f65404eb1388fcd568fcd702974c2b0c620bd155` | https://webrtc.googlesource.com/src/+/538442a75d7ed04c962f288f9aedc21562d22e6d/media/engine/webrtc_video_engine.cc | commit 538442a75d7ed04c962f288f9aedc21562d22e6d | identical |
| `v2/raw/chrome_webrtc_voice_engine.cc` | `be181e0ed91942b35627f8723b1101ceb98f57ddec7e3573625ff166d06f242e` | https://webrtc.googlesource.com/src/+/538442a75d7ed04c962f288f9aedc21562d22e6d/media/engine/webrtc_voice_engine.cc (reconstructed) | commit 538442a75d7ed04c962f288f9aedc21562d22e6d | identical |

## Janus documentation

License: GPL-3.0 (Janus documentation, generated by Doxygen from the GPL-3.0 sources).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/janus_admin.html` | `19388585fb58196860b708c730f24d44de3a25bf4821109c17758c682fa7b317` | https://janus.conf.meetecho.com/docs/admin.html | as served on the retrieval date | identical |
| `v2/raw/janus_admin.txt` | `3273de68c5da9143eb690bf7893076d3d562bbefd175d7f52722d19ed28ffda8` | https://janus.conf.meetecho.com/docs/admin.html | text of janus_admin.html | derived |
| `v2/raw/janus_eventhandlers.html` | `b6b6646d06750ccc2d67df912e6c2ae21eca3d81f70dc9407a6dcde31a1d4c6a` | https://janus.conf.meetecho.com/docs/eventhandlers.html (reconstructed) | as served on the retrieval date | identical |

## Janus WebRTC Server source

License: GPL-3.0 (Janus; copyright header in the file).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/janus_ice.c` | `445954d2be447c4a54839c7497efc7aef55a287bac3dc43ab0e81ddf4f4d25cc` | https://github.com/meetecho/janus-gateway/blob/master/src/ice.c (reconstructed) | branch master, commit not recorded | identical |
| `v2/raw/janus_ice.h` | `c6d9c335c09c895c57f2d0e86cdc9b9dbd1f6a296131d895f2954500900fdc27` | https://github.com/meetecho/janus-gateway/blob/master/src/ice.h | branch master, commit not recorded | identical |
| `v2/raw/janus_janus.c` | `5894623584711ee0d514d2b871eda1db856ff532f2f053e46b1e49037f43e749` | https://github.com/meetecho/janus-gateway/blob/master/src/janus.c | branch master, commit not recorded | identical |
| `v2/raw/janus_rtcp.c` | `77bb812d58320c41fbe11da39a17781ec659e051cbe87ee40e3d33ff942d7acd` | https://github.com/meetecho/janus-gateway/blob/master/src/rtcp.c (reconstructed) | branch master, commit not recorded | identical |
| `v2/raw/janus_rtcp.h` | `66e9dcc51fbd8e9510916752022f40bc62c8d1726e74d4eed0a9e46bd6d612a7` | https://github.com/meetecho/janus-gateway/blob/master/src/rtcp.h | branch master, commit not recorded | identical |

## Jitsi lib-jitsi-meet

License: Apache-2.0 (lib-jitsi-meet).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/jitsi_ConnectionQuality.ts` | `8d788c5e3f7be1be76de7aa36a6c669e1b5efd86b631e1a4933ac86be95fde35` | https://github.com/jitsi/lib-jitsi-meet/blob/7afa6544e90516ce68d06f5bd64af01779d8d02f/modules/connectivity/ConnectionQuality.ts (reconstructed) | commit 7afa6544e90516ce68d06f5bd64af01779d8d02f | identical |
| `v2/raw/jitsi_Events.ts` | `4f8d772e82dd4a3e12139ca7764082e7be5dc4aca8edc0a6582fc9c6b008673c` | https://github.com/jitsi/lib-jitsi-meet/blob/7afa6544e90516ce68d06f5bd64af01779d8d02f/service/statistics/Events.ts (reconstructed) | commit 7afa6544e90516ce68d06f5bd64af01779d8d02f | identical |
| `v2/raw/jitsi_RTPStatsCollector.js` | `0fa6c55e5a3f490445e6cc283d38c90f8c75290546338b57c1e187ecb508f2d2` | https://github.com/jitsi/lib-jitsi-meet/blob/7afa6544e90516ce68d06f5bd64af01779d8d02f/modules/statistics/RTPStatsCollector.js | commit 7afa6544e90516ce68d06f5bd64af01779d8d02f | identical |

## LiveKit source

License: Apache-2.0 (LiveKit; license header in the file).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/livekit_livekit_analytics.proto` | `a828ff2a4e6428785765feac265d55b017a9b93c612c62581c4b2e6b16d1b692` | https://github.com/livekit/protocol/blob/main/protobufs/livekit_analytics.proto (reconstructed) | branch main, commit not recorded | identical |
| `v2/raw/livekit_livekit_rtc.proto` | `b15cdd37f7a3c84caed7c00b8177bd196235ced118e31a64511a9811d56ae928` | https://github.com/livekit/protocol/blob/main/protobufs/livekit_rtc.proto (reconstructed) | branch main, commit not recorded | identical |
| `v2/raw/livekit_models.proto` | `b629822026f977bf748c57833383730006a6cdd5af4a50e8cbb95c47816e5a42` | https://github.com/livekit/protocol/blob/main/protobufs/livekit_models.proto | branch main, commit not recorded | identical |
| `v2/raw/livekit_server_buffer.go` | `bc50b5637b642563ed7da802da77450e923aa3f04b0c2310fc5e54204aadf0d4` | https://github.com/livekit/livekit/blob/master/pkg/sfu/buffer/buffer.go (reconstructed) | branch master, commit not recorded | differs from the current upstream file (changed since retrieval) |
| `v2/raw/livekit_server_buffer_base.go` | `fef8a63fa442b8c5a4e43d90c8e63ad5c9e4ece899e712ce674b077cd834c084` | https://github.com/livekit/livekit/blob/master/pkg/sfu/buffer/buffer_base.go (reconstructed) | branch master, commit not recorded | differs from the current upstream file (changed since retrieval) |
| `v2/raw/livekit_server_rtpstats_base.go` | `8757c6c3375120bc62de9500756b0de9f9081c3155233f7824e1d313cbe59c9d` | https://github.com/livekit/livekit/blob/master/pkg/sfu/rtpstats/rtpstats_base.go | branch master, commit not recorded | identical |
| `v2/raw/livekit_server_rtpstats_base_lite.go` | `b60ddf58682326c34522ee64abe38667c539d61d1e480b1fcdc85966d7a602e9` | https://github.com/livekit/livekit/blob/master/pkg/sfu/rtpstats/rtpstats_base_lite.go | branch master, commit not recorded | identical |
| `v2/raw/livekit_server_rtpstats_receiver.go` | `6b7c3659adfa297297075588bbba8446c59b87d92aff66cc3f05b09367d05b26` | https://github.com/livekit/livekit/blob/master/pkg/sfu/rtpstats/rtpstats_receiver.go | branch master, commit not recorded | identical |

## mediasoup v3 source

License: ISC (mediasoup; see the repository LICENSE).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/mediasoup_src_RateCalculator.cpp` | `493587ee57095cbdc150974a12406b52d9201c30c325d6f51bd741992b7b102b` | https://github.com/versatica/mediasoup/blob/v3/worker/src/RTC/RateCalculator.cpp (reconstructed) | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |
| `v2/raw/mediasoup_src_RateCalculator.hpp` | `d67240427cfcb1781efb0707b9a8dcdd52f527a43db8c8a38aaa131e1739a357` | https://github.com/versatica/mediasoup/blob/v3/worker/include/RTC/RateCalculator.hpp | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |
| `v2/raw/mediasoup_src_RtpStream.cpp` | `92511a6186bed92bd3e4bff4439483a6d4c9aac181c2bea4145f8f4c60546c75` | https://github.com/versatica/mediasoup/blob/v3/worker/src/RTC/RTP/RtpStream.cpp | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |
| `v2/raw/mediasoup_src_RtpStreamRecv.cpp` | `0b624665e12374f4d5c137399b9322cd24c1cb9e582ceba5aa4bcd2b349bcd96` | https://github.com/versatica/mediasoup/blob/v3/worker/src/RTC/RTP/RtpStreamRecv.cpp | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |
| `v2/raw/mediasoup_src_Transport.cpp` | `3b5cc98f0b1791f8ba91c1dd47bebdb60002c567f8163be5926c741c447e46cb` | https://github.com/versatica/mediasoup/blob/v3/worker/src/RTC/Transport.cpp | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |
| `v2/raw/mediasoup_src_Transport.hpp` | `9297583e1d3b9e8e083e245ec7f72f7c851e5ed6b7885a206147ca84547fafc3` | https://github.com/versatica/mediasoup/blob/v3/worker/include/RTC/Transport.hpp (reconstructed) | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |
| `v2/raw/mediasoup_src_TransportCongestionControlServer.cpp` | `e9589f2ac09d779a8db83668206f5cc1de0134fc65fd02d5f86cd12fd86b2d21` | https://github.com/versatica/mediasoup/blob/v3/worker/src/RTC/TransportCongestionControlServer.cpp (reconstructed) | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |
| `v2/raw/mediasoup_src_TransportCongestionControlServer.hpp` | `efa0b256c1fbfb80e452b5585f20b0986d23d7713637582a49f792e41c1dd1f1` | https://github.com/versatica/mediasoup/blob/v3/worker/include/RTC/TransportCongestionControlServer.hpp (reconstructed) | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |
| `v2/raw/mediasoup_src_WebRtcTransport.cpp` | `73c8c200d35425318031284bccd5a4618470aaa26bd81e110c491a064a1f36a1` | https://github.com/versatica/mediasoup/blob/v3/worker/src/RTC/WebRtcTransport.cpp (reconstructed) | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |
| `v2/raw/mediasoup_src_rtpStreamStatsTypes.ts` | `3554a377f08391ec267d7213e115962b7dde132d82c8c518e04ab48ee462023a` | https://github.com/versatica/mediasoup/blob/v3/node/src/rtpStreamStatsTypes.ts (reconstructed) | branch v3, tree 552fee8e02737a96f0e3fcb0f1683de68d62a106 | identical (git blob in tree 552fee8e) |

## ns-3 FlowMonitor

License: GPL-2.0-only (ns-3; SPDX identifier in the file).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/ns3_flow-monitor.cc` | `e9e7d485b989356a5b4e425a4a6f3a4df80d7afa168ebe62dc326171e64b5397` | https://gitlab.com/nsnam/ns-3-dev/-/blob/master/src/flow-monitor/model/flow-monitor.cc (reconstructed) | branch master, commit not recorded | identical |
| `v2/raw/ns3_flow-monitor.h` | `52d8532dc1ab56975d69a38e6203869cf97b4ce5699c7fceef70ea7e779af0f3` | https://gitlab.com/nsnam/ns-3-dev/-/blob/master/src/flow-monitor/model/flow-monitor.h | branch master, commit not recorded | identical |

## ns-3 model library documentation

License: GPL-2.0-only (ns-3 model documentation, built from the ns-3 source tree).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/ns3_flowmonitor.html` | `ab00558456ddb14ed16f8eb062a92e114f3afb729679116d3ee320180ce59f5d` | https://www.nsnam.org/docs/models/html/flow-monitor.html | as served on the retrieval date | differs from the current upstream file (changed since retrieval) |
| `v2/raw/ns3_flowmonitor.txt` | `d117d5796d1551c43894343c1bc78daa4afab7d830c0b43051cf6cbc811d89ac` | https://www.nsnam.org/docs/models/html/flow-monitor.html | text of ns3_flowmonitor.html | derived |

## Pion WebRTC source

License: MIT (Pion; SPDX identifier in the file).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/pion_dtlstransport.go` | `6f92a94ef815dbc842d19fd0c7b5927f42666c321191127d28595da340fd4f5c` | https://github.com/pion/webrtc/blob/master/dtlstransport.go (reconstructed) | branch master (v4), commit not recorded | identical |
| `v2/raw/pion_icegatherer.go` | `8b5b86bcc636e1e4eb95836c02d6e739416aecb68a6bc2f5ceb59897e5672c90` | https://github.com/pion/webrtc/blob/master/icegatherer.go (reconstructed) | branch master (v4), commit not recorded | identical |
| `v2/raw/pion_icetransport.go` | `94e4c47b10d06694e98064c1d032f6da8bcaa418a778d1b29c173e3659c465d9` | https://github.com/pion/webrtc/blob/master/icetransport.go (reconstructed) | branch master (v4), commit not recorded | identical |
| `v2/raw/pion_peerconnection.go` | `0a475c205c78b93918095a12be3f5e841b84608088d5c1016ced3fefdc437472` | https://github.com/pion/webrtc/blob/master/peerconnection.go (reconstructed) | branch master (v4), commit not recorded | identical |
| `v2/raw/pion_rtpreceiver.go` | `e7f4ff99b117ea79afc003e89fc7d543a7be5b11579ef49ba2f904cca59dd219` | https://github.com/pion/webrtc/blob/master/rtpreceiver.go (reconstructed) | branch master (v4), commit not recorded | identical |
| `v2/raw/pion_stats.go` | `fac48033598ad67eaa14a4c103f15de6f348518aa25e8eadefe766845c40f24c` | https://github.com/pion/webrtc/blob/master/stats.go | branch master (v4), commit not recorded | identical |
| `v2/raw/pion_stats_go.go` | `dac9f7ecbb7a65f9c34da939380d7ffee1d3a527e8a54961e0ddc0eebd54be6c` | https://github.com/pion/webrtc/blob/master/stats_go.go (reconstructed) | branch master (v4), commit not recorded | identical |

## SRT statistics documentation

License: MPL-2.0 (SRT repository).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/srt_statistics.md` | `62f0f9449f38706e2dd7198f115947d96d24e1ae1f72230abf0cfbecc1c2c651` | https://github.com/Haivision/srt/blob/master/docs/API/statistics.md | branch master, commit not recorded | identical |

## twilio-video.js source

License: BSD-3-Clause (twilio-video.js; see the repository LICENSE).

| File | SHA-256 | URL | Version | Upstream check |
|---|---|---|---|---|
| `v2/raw/twilio_src_getstats.js` | `6eab6fe31df212cd39e7197d8087d18c47ed5bcfc58395ea538c24c588088315` | https://github.com/twilio/twilio-video.js/blob/master/lib/webrtc/getstats.js (reconstructed) | branch master, commit not recorded | identical |
| `v2/raw/twilio_src_nqbandwidth.js` | `2e9f6762d5887d128e93240c1a01c3bc8866d14c06dd194ec9052784708b1abe` | https://github.com/twilio/twilio-video.js/blob/master/lib/stats/networkqualitybandwidthstats.js (reconstructed) | branch master, commit not recorded | identical |
| `v2/raw/twilio_src_receiverreport.js` | `00047cc503c6a514e46c3c73aabd351052ee4f2bc1a9df00134ef145d784987e` | https://github.com/twilio/twilio-video.js/blob/master/lib/stats/receiverreport.js | branch master, commit not recorded | identical |
| `v2/raw/twilio_src_receiverreportfactory.js` | `5ea05d11810280e381f52d08e1d500247f3ac4824d4fc667a747e28bfd2cc26e` | https://github.com/twilio/twilio-video.js/blob/master/lib/stats/receiverreportfactory.js (reconstructed) | branch master, commit not recorded | identical |
| `v2/raw/twilio_src_remotetrackstats.js` | `c64681e73c76461c5ae9d77c83ac8f0a64fee2da35b67f54ff17b693b53dd510` | https://github.com/twilio/twilio-video.js/blob/master/lib/stats/remotetrackstats.js (reconstructed) | branch master, commit not recorded | identical |
| `v2/raw/twilio_src_senderorreceiverreportfactory.js` | `050d124cbe6efb8e6fc120429965ca3aa5a8ab69a12fef7bf14820fbbfe63959` | https://github.com/twilio/twilio-video.js/blob/master/lib/stats/senderorreceiverreportfactory.js (reconstructed) | branch master, commit not recorded | identical |
| `v2/raw/twilio_src_statsreport.js` | `57d7c5a558301782738829f2cd874a8d7fb4106e402b3a732374ffa8ba93ffcf` | https://github.com/twilio/twilio-video.js/blob/master/lib/stats/statsreport.js (reconstructed) | branch master, commit not recorded | identical |
| `v2/raw/twilio_src_trackstats.js` | `ecee5224bec3921cfac6125338f0cc3c5bb35c1ac839adc2c70edb6357857af9` | https://github.com/twilio/twilio-video.js/blob/master/lib/stats/trackstats.js (reconstructed) | branch master, commit not recorded | identical |

## Our helper and provenance notes

| File | SHA-256 | Content |
|---|---|---|
| `v1/raw/h2t.py` | `26089a0b5b488b59583a07b797e3c9916d2543bdcefb97d77a7365544a5b8698` | our helper |
| `v2/raw/chrome_commit.txt` | `aa4eaa8a46d49dcf670622756922a447cd869f9e17c13c01db8f79098e32c5bd` | our provenance note |
| `v2/raw/jitsi_commit_sha.txt` | `b7955e293c9f36c4c64b4e9a0b08888ab6d56733e894a7ac61c823711adaf38c` | our provenance note |
| `v2/raw/mediasoup_tree_sha.txt` | `493f3ecc88af7879f8f9d94dcccb143c084d7c1fd568a9561022dd4c0c2188f0` | our provenance note |
| `v2/raw/pion_commit_sha.txt` | `65db8f7aa621712c9f7dd242b341722d433718688b3d0365304c7a16ed466658` | our provenance note |

## Sources read but not released

These pages were read for the transcriptions but are not redistributable, or their license was not verified. The transcriptions quote the
text that the ground truth relies on and give the URL of every field. Closest Wayback Machine snapshots, where one exists, are listed;
they predate our retrieval and may differ from what we read.

| Source | URL | Reason | Archived copy |
|---|---|---|---|
| RFC Editor errata page for RFC 3611 | https://www.rfc-editor.org/errata/rfc3611 | RFC Editor web page, whose terms we did not check. The transcription cites erratum 2262 (https://www.rfc-editor.org/errata/eid2262). | http://web.archive.org/web/20260123210342/https://www.rfc-editor.org/errata/rfc3611 |
| GStreamer rtpmanager | https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/main/subprojects/gst-plugins-good/gst/rtpmanager/rtptwccstats.c | failed fetch: the file holds a GitLab 'Not Found' page, not the source | none found |
| Agora Web SDK API reference 4.x | https://api-ref.agora.io/en/video-sdk/web/4.x/interfaces/agorartcstats.html | Agora documentation pages are not redistributable | none found |
| Agora Web SDK API reference 4.x | https://api-ref.agora.io/en/video-sdk/web/4.x/interfaces/iagorartcclient.html | Agora documentation pages are not redistributable | none found |
| Agora Web SDK API reference 4.x | https://api-ref.agora.io/en/video-sdk/web/4.x/interfaces/networkquality.html | Agora documentation pages are not redistributable | none found |
| Agora Web SDK API reference 4.x | https://api-ref.agora.io/en/video-sdk/web/4.x/interfaces/remoteaudiotrackstats.html | Agora documentation pages are not redistributable | none found |
| Agora Web SDK API reference 4.x | https://api-ref.agora.io/en/video-sdk/web/4.x/interfaces/remotevideotrackstats.html | Agora documentation pages are not redistributable | http://web.archive.org/web/20251113061252/https://api-ref.agora.io/en/video-sdk/web/4.x/interfaces/remotevideotrackstats.html |
| Daily daily-js reference | https://docs.daily.co/reference/daily-js/instance-methods/get-network-stats | Daily documentation pages are not redistributable | http://web.archive.org/web/20260521135006/https://docs.daily.co/reference/daily-js/instance-methods/get-network-stats |
| mediasoup v3 documentation site | https://mediasoup.org/documentation/v3/mediasoup/rtc-statistics/ | the mediasoup.org site is not covered by the ISC license of the source | http://web.archive.org/web/20250618042952/https://mediasoup.org/documentation/v3/mediasoup/rtc-statistics/ |
| pkg.go.dev page of github.com/pion/webrtc/v4 | https://pkg.go.dev/github.com/pion/webrtc/v4 | pkg.go.dev pages are not redistributable | http://web.archive.org/web/20260228173538/https://pkg.go.dev/github.com/pion/webrtc/v4 |
| Microsoft Teams Call Quality Dashboard documentation | https://learn.microsoft.com/en-us/microsoftteams/dimensions-and-measures-available-in-call-quality-dashboard | license not verified | http://web.archive.org/web/20260814001732/https://learn.microsoft.com/en-us/microsoftteams/dimensions-and-measures-available-in-call-quality-dashboard |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/LocalTrackStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/NetworkQualityAudioStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/NetworkQualityBandwidthStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/NetworkQualityFractionLostStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/NetworkQualityLatencyStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/NetworkQualityMediaStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/NetworkQualityRecvStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/NetworkQualitySendOrRecvStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/NetworkQualityStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/NetworkQualityVideoStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/RemoteAudioTrackStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/RemoteTrackStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/RemoteVideoTrackStats.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/Room.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/StatsReport.html | Twilio documentation pages are not redistributable | none found |
| Twilio Video JS 2.36.0 API documentation | https://sdk.twilio.com/js/video/releases/2.36.0/docs/TrackStats.html | Twilio documentation pages are not redistributable | none found |

The RFC 3611 erratum cited by the transcription is https://www.rfc-editor.org/errata/eid2262 (archived: http://web.archive.org/web/20260210215354/https://www.rfc-editor.org/errata/eid2262).
