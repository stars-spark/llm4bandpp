# -*- coding: utf-8 -*-
"""Estimator gcc_pt125: OpenNetLab Python GCC with its loss branch reading payload type 125.
The original loss branch counts only payload type 126; on this testbed video is 125 and retransmission 122, so that branch sees no data and the minimum of the two branches never rises. Formulas and the rest are inherited from estimator/gcc.py.
"""
from estimator.gcc import GCCEstimator


class GCCEstimatorPT125(GCCEstimator):
    VIDEO_PT = 125

    def caculate_loss_rate(self):
        flag = False
        valid_packets_num = 0
        min_sequence_number, max_sequence_number = 0, 0
        if len(self.packets_list) == 0:
            return -1
        for i in range(len(self.packets_list)):
            if self.packets_list[i].payload_type == self.VIDEO_PT:
                if not flag:
                    min_sequence_number = self.packets_list[i].sequence_number
                    max_sequence_number = self.packets_list[i].sequence_number
                    flag = True
                valid_packets_num += 1
                min_sequence_number = min(min_sequence_number, self.packets_list[i].sequence_number)
                max_sequence_number = max(max_sequence_number, self.packets_list[i].sequence_number)
        if (max_sequence_number - min_sequence_number) == 0:
            return -1
        receive_rate = valid_packets_num / (max_sequence_number - min_sequence_number)
        loss_rate = 1 - receive_rate
        return loss_rate
