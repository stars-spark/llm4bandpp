# lowbw_trap_300_1000: 300 and 1000 kbps alternate every 20 s, latency 50 ms, packet loss 0%, 120 s. saturated and not saturated alternate, to see whether the switcher locks onto the conservative arm.
rate 300
delay 50
loss 0
wait 20
rate 1000
wait 20
rate 300
wait 20
rate 1000
wait 20
rate 300
wait 20
rate 1000
wait 20
