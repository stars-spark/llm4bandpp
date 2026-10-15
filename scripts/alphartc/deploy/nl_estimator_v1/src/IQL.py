# source: https://github.com/gwthomas/IQL-PyTorch
# https://arxiv.org/pdf/2110.06169.pdf
import copy
import os
import random
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from tqdm import tqdm

import numpy as np
import pyrallis
import torch
import torch.nn as nn
import torch.nn.functional as F
import wandb
from torch.distributions import Normal
from torch.optim.lr_scheduler import CosineAnnealingLR
import pickle
import json
import onnxruntime as ort

from estimator import bwe_agent
import datetime

TensorBatch = List[torch.Tensor]
pickle_path = '/path/to/challenge/solution/dataset/training_dataset_pickle/MRE/MRE_4.pickle'
evaluation_dataset_path = '/path/to/challenge/solution/evaluate_dataset'
ENUM = 120  # every 5 evaluation set
small_evaluation_datasets = []
evaluate_dataset_file_names = os.listdir(evaluation_dataset_path)
for e_f_name in evaluate_dataset_file_names[:ENUM]:
    e_f_path = os.path.join(evaluation_dataset_path, e_f_name)
    small_evaluation_datasets.append(e_f_path)

os.environ['CUDA_VISIBLE_DEVICES'] = '0, 1'
USE_WANDB = 0
b_in_Mb = 1e6

MAX_ACTION = 20  # Mbps
STATE_DIM = 150
ACTION_DIM = 1

EXP_ADV_MAX = 100.0
LOG_STD_MIN = -20.0
LOG_STD_MAX = 2.0

# ROBUST_CAPACITY_ANCHORED_IQL_V1
def relabel_hcq_reward(
    actions_bps: np.ndarray,
    capacities_bps: np.ndarray,
    source_rewards: np.ndarray,
    mode: str,
    source_lambda: float,
    target_lambda: float,
    error_cap: float,
):
    # Reconstruct QoE from the source HCQ reward, then optionally cap its MRE tail.
    if not 0.0 <= source_lambda < 1.0:
        raise ValueError("source_reward_lambda must be in [0, 1)")
    if not 0.0 <= target_lambda <= 1.0:
        raise ValueError("reward_lambda must be in [0, 1]")
    if error_cap <= 0.0:
        raise ValueError("reward_error_cap must be positive")

    actions = np.asarray(actions_bps, dtype=np.float64).reshape(-1)
    capacities = np.asarray(capacities_bps, dtype=np.float64).reshape(-1)
    rewards = np.asarray(source_rewards, dtype=np.float64).reshape(-1)
    if not (actions.shape == capacities.shape == rewards.shape):
        raise ValueError("actions, capacities, and rewards must have equal length")

    valid = (
        np.isfinite(actions)
        & np.isfinite(capacities)
        & np.isfinite(rewards)
        & (capacities > 0.0)
    )
    relative_error = np.full_like(rewards, np.nan)
    relative_error[valid] = (
        np.abs(actions[valid] - capacities[valid])
        / (capacities[valid] + 1e-6)
    )

    if mode == "original":
        output = rewards.copy()
    elif mode == "capped_mre":
        qoe = np.full_like(rewards, np.nan)
        qoe[valid] = (
            rewards[valid] + source_lambda * relative_error[valid]
        ) / (1.0 - source_lambda)
        robust_error = np.minimum(relative_error, error_cap)
        output = (1.0 - target_lambda) * qoe - target_lambda * robust_error
    else:
        raise ValueError(f"unsupported reward_mode: {mode}")

    valid &= np.isfinite(output)
    finite_errors = relative_error[valid]
    audit = {
        "mode": mode,
        "source_lambda": float(source_lambda),
        "target_lambda": float(target_lambda),
        "error_cap": float(error_cap),
        "rows_total": int(rewards.size),
        "rows_valid": int(valid.sum()),
        "rows_removed": int((~valid).sum()),
        "tail_rows_capped": int((finite_errors > error_cap).sum()),
        "relative_error_p50": float(np.median(finite_errors)),
        "relative_error_p99": float(np.quantile(finite_errors, 0.99)),
        "source_reward_min": float(np.min(rewards[valid])),
        "new_reward_min": float(np.min(output[valid])),
        "new_reward_max": float(np.max(output[valid])),
    }
    return (
        output.astype(np.float32),
        (capacities / b_in_Mb).astype(np.float32),
        valid,
        audit,
    )


@dataclass
class TrainConfig:
    # Experiment
    device: str = "cuda:6"
    env: str = "qwen1.5lora-dual-MRE8"
    seed: int = 0  # Sets Gym, PyTorch and Numpy seeds
    eval_freq: int = int(1e4)  # How often (time steps) we evaluate
    max_timesteps: int = int(1e6) # Max time steps to run environment
    checkpoints_path: Optional[str] = './checkpoints_iql/MRE'  # Save path
    load_model: str = ""  # Model load file name, "" doesn't load
    # IQL
    buffer_size: int = 18_538_000  # Replay buffer size
    batch_size: int = 512  # Batch size for all networks
    discount: float = 0.99  # Discount factor
    tau: float = 0.005  # Target network update rate
    beta: float = 3.0  # Inverse temperature. Small beta -> BC, big beta -> maximizing Q
    iql_tau: float = 0.7  # Coefficient for asymmetric loss
    iql_deterministic: bool = False  # Use deterministic actor
    vf_lr: float = 3e-4  # V function learning rate
    qf_lr: float = 3e-4  # Critic learning rate
    actor_lr: float = 3e-4  # Actor learning rate
    actor_dropout: Optional[float] = None  # Adroit uses dropout for policy network
    # Robust capacity-anchored IQL. The source pickle remains MRE_4.
    reward_mode: str = "capped_mre"
    source_reward_lambda: float = 0.4
    reward_lambda: float = 0.4
    reward_error_cap: float = 5.0
    capacity_aux_weight: float = 1.0
    capacity_huber_delta: float = 1.0
    # Wandb logging
    project: str = "bwe-llama"
    group: str = "IQL"
    name: str = "IQL"

    def __post_init__(self):
        self.name = f"{self.name}-{self.env}-{str(uuid.uuid4())[:8]}"
        if self.checkpoints_path is not None:
            self.checkpoints_path = os.path.join(self.checkpoints_path, self.name)

def soft_update(target: nn.Module, source: nn.Module, tau: float):
    for target_param, source_param in zip(target.parameters(), source.parameters()):
        target_param.data.copy_((1 - tau) * target_param.data + tau * source_param.data)

class ReplayBuffer:
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        buffer_size: int,
        device: str = "cpu",
        reward_mode: str = "original",
        source_reward_lambda: float = 0.4,
        reward_lambda: float = 0.4,
        reward_error_cap: float = 5.0,
    ):
        self._buffer_size = buffer_size
        self._reward_mode = reward_mode
        self._source_reward_lambda = source_reward_lambda
        self._reward_lambda = reward_lambda
        self._reward_error_cap = reward_error_cap
        self._pointer = 0
        self._size = 0

        self._states = torch.zeros(
            (buffer_size, state_dim), dtype=torch.float32, device=device
        )
        self._actions = torch.zeros(
            (buffer_size, action_dim), dtype=torch.float32, device=device
        )
        self._rewards = torch.zeros((buffer_size, 1), dtype=torch.float32, device=device)
        self._capacities = torch.zeros((buffer_size, 1), dtype=torch.float32, device=device)
        self._next_states = torch.zeros(
            (buffer_size, state_dim), dtype=torch.float32, device=device
        )
        self._dones = torch.zeros((buffer_size, 1), dtype=torch.float32, device=device)
        self._device = device

    def _to_tensor(self, data: np.ndarray) -> torch.Tensor:
        return torch.tensor(data, dtype=torch.float32, device=self._device)

    # Loads data in d4rl format, i.e. from Dict[str, np.array].
    def load_dataset(self, data: Dict[str, np.ndarray]):
        if self._size != 0:
            raise ValueError("Trying to load data into non-empty replay buffer")
        required = {
            "observations", "actions", "rewards", "next_observations",
            "terminals", "true_capacitys",
        }
        missing = required.difference(data)
        if missing:
            raise KeyError(f"dataset lacks required keys: {sorted(missing)}")
        rewards, capacities, valid, audit = relabel_hcq_reward(
            data["actions"], data["true_capacitys"], data["rewards"],
            self._reward_mode, self._source_reward_lambda,
            self._reward_lambda, self._reward_error_cap,
        )
        n_transitions = int(valid.sum())
        print("REWARD_AUDIT " + json.dumps(audit, sort_keys=True))
        if n_transitions > self._buffer_size:
            raise ValueError("Replay buffer is smaller than the valid dataset!")
        self._states[:n_transitions] = self._to_tensor(
            np.asarray(data["observations"])[valid]
        )
        self._actions[:n_transitions] = self._to_tensor(
            np.asarray(data["actions"])[valid] / b_in_Mb
        )
        self._rewards[:n_transitions] = self._to_tensor(rewards[valid, None])
        self._capacities[:n_transitions] = self._to_tensor(capacities[valid, None])
        self._next_states[:n_transitions] = self._to_tensor(
            np.asarray(data["next_observations"])[valid]
        )
        terminals = np.asarray(data["terminals"]).reshape(-1)
        self._dones[:n_transitions] = self._to_tensor(terminals[valid, None])
        self._size = n_transitions
        self._pointer = n_transitions

    def sample(self, batch_size: int) -> TensorBatch:
        indices = np.random.randint(0, min(self._size, self._pointer), size=batch_size)
        states = self._states[indices]
        actions = self._actions[indices]
        rewards = self._rewards[indices]
        next_states = self._next_states[indices]
        dones = self._dones[indices]
        capacities = self._capacities[indices]
        return [states, actions, rewards, next_states, dones, capacities]

    def add_transition(self):
        # Use this method to add new data into the replay buffer during fine-tuning.
        # I left it unimplemented since now we do not do fine-tuning.
        raise NotImplementedError

def set_seed(
    seed: int, deterministic_torch: bool = False
):
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(deterministic_torch)

def wandb_init(config: dict) -> None:
    wandb.init(
        config=config,
        project=config["project"],
        group=config["group"],
        name=config["name"],
        id=str(uuid.uuid4()),
    )
    wandb.run.save()

def asymmetric_l2_loss(u: torch.Tensor, tau: float) -> torch.Tensor:
    return torch.mean(torch.abs(tau - (u < 0).float()) * u**2)

class Squeeze(nn.Module):
    def __init__(self, dim=-1):
        super().__init__()
        self.dim = dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x.squeeze(dim=self.dim)

class MLP(nn.Module):
    def __init__(
        self,
        dims,
        activation_fn: Callable[[], nn.Module] = nn.ReLU,
        output_activation_fn: Callable[[], nn.Module] = None,
        squeeze_output: bool = False,
        dropout: Optional[float] = None,
    ):
        super().__init__()
        n_dims = len(dims)
        if n_dims < 2:
            raise ValueError("MLP requires at least two dims (input and output)")

        layers = []
        for i in range(n_dims - 2):
            layers.append(nn.Linear(dims[i], dims[i + 1]))
            layers.append(activation_fn())

            if dropout is not None:
                layers.append(nn.Dropout(dropout))

        layers.append(nn.Linear(dims[-2], dims[-1]))
        if output_activation_fn is not None:
            layers.append(output_activation_fn())
        if squeeze_output:
            if dims[-1] != 1:
                raise ValueError("Last dim must be 1 when squeezing")
            layers.append(Squeeze(-1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

class GaussianPolicy(nn.Module):
    def __init__(
        self,
        state_dim: int,
        act_dim: int,
        max_action: float,
        hidden_dim: int = 256,
        n_hidden: int = 2,
        dropout: Optional[float] = None,
    ):
        super().__init__()
        self.log_std = nn.Parameter(torch.zeros(act_dim, dtype=torch.float32))
        self.max_action = max_action
        self.encoder0 = nn.Parameter(torch.tensor([1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 
                                 1e-4, 1e-4, 1e-4, 1e-4, 1e-4, 1e-5, 1e-5, 1e-5, 1e-5, 1e-5, 
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 
                                 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 
                                 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1,
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1,
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1
                                 ], dtype=torch.float32))
        self.encoder0.requires_grad_(False)

        # encoder 1
        self.encoder1 = nn.Sequential(
            # encoder 1
            nn.Linear(150, 256),
            # nn.LayerNorm(256),
            nn.ReLU()
        )
        # GRU
        self.gru = nn.GRU(256, 256, 2)
        # FC
        self.fc_mid = nn.Sequential(
            nn.Linear(256, 256),
            nn.ReLU()
        )
        # Recisual Block 1(rb1)
        self.rb1 = nn.Sequential(
            nn.Linear(256, 256),
            nn.LeakyReLU(),
            nn.Linear(256, 256),
            nn.LeakyReLU()
        )
        # Recisual Block 2(rb2)
        self.rb2 = nn.Sequential(
            nn.Linear(256, 256),
            nn.LeakyReLU(),
            nn.Linear(256, 256),
            nn.LeakyReLU()
        )
        # final 'gmm'
        self.final = nn.Sequential(
            nn.Linear(256, 1),
            nn.Tanh()
        )

    def forward(self, obs: torch.Tensor, h, c):
        obs_ = torch.squeeze(obs, 0)
        obs_ = obs_ * self.encoder0
###
        mean = self.encoder1(obs_)
        mean, _ = self.gru(mean)
        mean = self.fc_mid(mean)
        mem1 = mean
        mean = self.rb1(mean) + mem1
        mem2 = mean
        mean = self.rb2(mean) + mem2
        mean = self.final(mean)
###
        mean = mean * self.max_action * 1e6  # Mbps -> bps
        mean = mean.clamp(min = 10)  # larger than 10bps
        std = torch.exp(self.log_std.clamp(LOG_STD_MIN, LOG_STD_MAX))
        std = std.expand(mean.shape[0], 1)
        ret = torch.cat((mean, std), 1)
        ret = torch.unsqueeze(ret, 0)  # (1, bs, 2)
        return ret, h, c

class DeterministicPolicy(nn.Module):
    def __init__(
        self,
        state_dim: int,
        act_dim: int,
        max_action: float,
        hidden_dim: int = 256,
        n_hidden: int = 2,
        dropout: Optional[float] = None,
    ):
        super().__init__()
        self.net = MLP(
            [state_dim, *([hidden_dim] * n_hidden), act_dim],
            output_activation_fn=nn.Tanh,
            dropout=dropout,
        )
        self.max_action = max_action

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.net(obs)

    @torch.no_grad()
    def act(self, state: np.ndarray, device: str = "cpu"):
        state = torch.tensor(state.reshape(1, -1), device=device, dtype=torch.float32)
        return (
            torch.clamp(self(state) * self.max_action, -self.max_action, self.max_action)
            .cpu()
            .data.numpy()
            .flatten()
        )

class TwinQ(nn.Module):
    def __init__(
        self, state_dim: int, action_dim: int, hidden_dim: int = 256, n_hidden: int = 2
    ):
        super().__init__()
        dims = [state_dim + action_dim, *([hidden_dim] * n_hidden), 1]
        self.q1 = MLP(dims, squeeze_output=True)
        self.q2 = MLP(dims, squeeze_output=True)
        self.encoder = nn.Parameter(torch.tensor([1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 
                                 1e-4, 1e-4, 1e-4, 1e-4, 1e-4, 1e-5, 1e-5, 1e-5, 1e-5, 1e-5, 
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 
                                 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 
                                 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1,
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1,
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1
                                 ], dtype=torch.float32))
        self.encoder.requires_grad_(False)

    def both(self, state: torch.Tensor, action: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        state_ = state * self.encoder
        sa = torch.cat([state_, action], 1)
        return self.q1(sa), self.q2(sa)

    def forward(self, state: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        return torch.min(*self.both(state, action))

class ValueFunction(nn.Module):
    def __init__(self, state_dim: int, hidden_dim: int = 256, n_hidden: int = 2):
        super().__init__()
        dims = [state_dim, *([hidden_dim] * n_hidden), 1]
        self.v = MLP(dims, squeeze_output=True)
        self.encoder = nn.Parameter(torch.tensor([1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 
                                 1e-4, 1e-4, 1e-4, 1e-4, 1e-4, 1e-5, 1e-5, 1e-5, 1e-5, 1e-5, 
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 
                                 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 
                                 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 1e-2, 
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1,
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1,
                                 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1, 1e-1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1,
                                 1,    1,    1,    1,    1,    1,    1,    1,    1,    1
                                 ], dtype=torch.float32))
        self.encoder.requires_grad_(False)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        state_ = state * self.encoder
        return self.v(state_)


class ImplicitQLearning:
    def __init__(
        self,
        max_action: float,
        actor: nn.Module,
        actor_optimizer: torch.optim.Optimizer,
        q_network: nn.Module,
        q_optimizer: torch.optim.Optimizer,
        v_network: nn.Module,
        v_optimizer: torch.optim.Optimizer,
        iql_tau: float = 0.7,
        beta: float = 3.0,
        max_steps: int = 1000000,
        discount: float = 0.99,
        tau: float = 0.005,
        device: str = "cpu",
        capacity_aux_weight: float = 0.0,
        capacity_huber_delta: float = 1.0,
    ):
        self.max_action = max_action
        self.qf = q_network
        self.q_target = copy.deepcopy(self.qf).requires_grad_(False).to(device)
        self.vf = v_network
        self.actor = actor
        self.v_optimizer = v_optimizer
        self.q_optimizer = q_optimizer
        self.actor_optimizer = actor_optimizer
        self.actor_lr_schedule = CosineAnnealingLR(self.actor_optimizer, max_steps)
        self.iql_tau = iql_tau
        self.beta = beta
        self.discount = discount
        self.tau = tau
        self.capacity_aux_weight = capacity_aux_weight
        self.capacity_huber_delta = capacity_huber_delta

        self.total_it = 0
        self.device = device

    def _update_v(self, observations, actions, log_dict) -> torch.Tensor:
        # Update value function
        with torch.no_grad():
            target_q = self.q_target(observations, actions)

        v = self.vf(observations)
        adv = target_q - v
        v_loss = asymmetric_l2_loss(adv, self.iql_tau)
        log_dict["value_loss"] = v_loss.item()
        self.v_optimizer.zero_grad()
        v_loss.backward()
        self.v_optimizer.step()
        return adv

    def _update_q(
        self,
        next_v: torch.Tensor,
        observations: torch.Tensor,
        actions: torch.Tensor,
        rewards: torch.Tensor,
        terminals: torch.Tensor,
        log_dict: Dict,
    ):
        targets = rewards + (1.0 - terminals.float()) * self.discount * next_v.detach()
        qs = self.qf.both(observations, actions)
        q_loss = sum(F.mse_loss(q, targets) for q in qs) / len(qs)
        # log_dict["q_rewards"] = torch.mean(rewards).item()
        # log_dict["q_targets"] = torch.mean(targets).item()
        log_dict["q_score"] = (torch.mean(qs[0]).item() + torch.mean(qs[1]).item()) / 2
        log_dict["q_loss"] = q_loss.item()
        self.q_optimizer.zero_grad()
        q_loss.backward()
        self.q_optimizer.step()

        # Update target Q network
        soft_update(self.q_target, self.qf, self.tau)

    def _update_policy(
        self,
        adv: torch.Tensor,
        observations: torch.Tensor,
        actions: torch.Tensor,
        capacities: torch.Tensor,
        log_dict: Dict,
    ):
        exp_adv = torch.exp(self.beta * adv.detach()).clamp(max=EXP_ADV_MAX)
        out_, std = self.actor(observations)
        # print(out_.logits.shape) [batch_size, sequence_length, 1]
        # out_ = out_.logits[:, 149, :]  # using the prediction of total tokens as bwe -->[batch_size, 1, 1]   
        # out_ = torch.squeeze(out_, dim = 1) # -->[2] bwe
        # print(out_.shape)
        # out_ = torch.squeeze(out_, 0)
        # mean = out_[:, :1]
        mean = out_
        mean = mean / 1e6 
        policy_out = Normal(mean, std)
        if isinstance(policy_out, torch.distributions.Distribution):
            bc_losses = -policy_out.log_prob(actions).sum(-1, keepdim=False)
        elif torch.is_tensor(policy_out):
            if policy_out.shape != actions.shape:
                raise RuntimeError("Actions shape missmatch")
            bc_losses = torch.sum((policy_out - actions) ** 2, dim=1)
        else:
            raise NotImplementedError
        awr_loss = torch.mean(exp_adv * bc_losses)
        capacity_losses = F.smooth_l1_loss(
            mean, capacities, beta=self.capacity_huber_delta, reduction="none"
        ).sum(dim=-1)
        capacity_loss = torch.mean(capacity_losses)
        policy_loss = awr_loss + self.capacity_aux_weight * capacity_loss
        log_dict["actor_awr_loss"] = awr_loss.item()
        log_dict["actor_capacity_loss"] = capacity_loss.item()
        log_dict["actor_all_loss"] = policy_loss.item()
        # log_dict["actor_bc_loss"] = torch.mean(bc_losses).item()
        # log_dict["actor_expadv_loss"] = torch.mean(exp_adv).item()
        self.actor_optimizer.zero_grad()
        policy_loss.backward()
        self.actor_optimizer.step()
        self.actor_lr_schedule.step()
        return policy_loss.detach()

    def train(self, batch: TensorBatch) -> Dict[str, float]:
        self.total_it += 1
        (
            observations,
            actions,
            rewards,
            next_observations,
            dones,
            capacities,
        ) = batch
        log_dict = {}

        # next state's score
        with torch.no_grad():
            next_v = self.vf(next_observations)
        # Update value function
        adv = self._update_v(observations, actions, log_dict)
        rewards = rewards.squeeze(dim=-1)
        dones = dones.squeeze(dim=-1)
        # Update Q function
        self._update_q(next_v, observations, actions, rewards, dones, log_dict)
        # Update actor
        policy_loss = self._update_policy(adv, observations, actions, capacities, log_dict)

        return log_dict, policy_loss

    def state_dict(self) -> Dict[str, Any]:
        return {
            "qf": self.qf.state_dict(),
            "q_optimizer": self.q_optimizer.state_dict(),
            "vf": self.vf.state_dict(),
            "v_optimizer": self.v_optimizer.state_dict(),
            "actor": self.actor.state_dict(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "actor_lr_schedule": self.actor_lr_schedule.state_dict(),
            "total_it": self.total_it,
        }

    def load_state_dict(self, state_dict: Dict[str, Any]):
        self.qf.load_state_dict(state_dict["qf"])
        self.q_optimizer.load_state_dict(state_dict["q_optimizer"])
        self.q_target = copy.deepcopy(self.qf)

        self.vf.load_state_dict(state_dict["vf"])
        self.v_optimizer.load_state_dict(state_dict["v_optimizer"])

        self.actor.load_state_dict(state_dict["actor"])
        self.actor_optimizer.load_state_dict(state_dict["actor_optimizer"])
        self.actor_lr_schedule.load_state_dict(state_dict["actor_lr_schedule"])

        self.total_it = state_dict["total_it"]


def get_input_from_file():
    # dummy -> real input
    evaluation_file = '../evaluation/data/02560.json'
    with open(evaluation_file, "r") as file:
        call_data = json.load(file)
    observations = np.asarray(call_data['observations'], dtype=np.float32)
    observations = observations.reshape(1, -1, STATE_DIM)
    return observations

def export2onnx(pt_path, onnx_path):
    """
    trans pt to onnx
    """
    BS = 1  # batch size
    hidden_size = 1  # number of hidden units in the LSTM

    # instantiate the ML BW estimator
    torchBwModel = bwe_agent(MAX_ACTION, STATE_DIM, ACTION_DIM, "cuda")
    torchBwModel.load_state_dict(torch.load(pt_path))
    # create inputs: 1 episode x T timesteps x obs_dim features
    dummy_inputs = get_input_from_file()
    torch_dummy_inputs = torch.as_tensor(dummy_inputs)
    torch_initial_hidden_state = torch.zeros((BS, hidden_size))
    torch_initial_cell_state = torch.zeros((BS, hidden_size))
    # predict dummy outputs: 1 episode x T timesteps x 2 (mean and std)
    dummy_outputs, final_hidden_state, final_cell_state = torchBwModel(torch_dummy_inputs, torch_initial_hidden_state, torch_initial_cell_state)
    # save onnx model
    os.makedirs(os.path.dirname(onnx_path), exist_ok=True)
    torchBwModel.to("cpu")
    torchBwModel.eval()
    torch.onnx.export(
        torchBwModel,
        (torch_dummy_inputs[0:1, 0:1, :], torch_initial_hidden_state, torch_initial_cell_state),
        onnx_path,
        opset_version=11,
        input_names=['obs', 'hidden_states', 'cell_states'], # the model's input names
        output_names=['output', 'state_out', 'cell_out'], # the model's output names
    )
    
    # verify torch and onnx models outputs
    ort_session = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
    onnx_hidden_state, onnx_cell_state = (np.zeros((1, hidden_size), dtype=np.float32), np.zeros((1, hidden_size), dtype=np.float32))
    torch_hidden_state, torch_cell_state = (torch.as_tensor(onnx_hidden_state), torch.as_tensor(onnx_cell_state))
    # online interaction: step through the environment 1 time step at a time
    with torch.no_grad():
        for i in tqdm(range(dummy_inputs.shape[1]), desc="Verifing  "):
            torch_estimate, torch_hidden_state, torch_cell_state = torchBwModel(torch_dummy_inputs[0:1, i:i+1, :], torch_hidden_state, torch_cell_state)
            feed_dict= {'obs': dummy_inputs[0:1, i:i+1, :], 'hidden_states': onnx_hidden_state, 'cell_states': onnx_cell_state}
            onnx_estimate, onnx_hidden_state, onnx_cell_state = ort_session.run(None, feed_dict)
            assert np.allclose(torch_estimate.numpy(), onnx_estimate, atol=10), 'Failed to match model outputs!, {}, {}'.format(torch_estimate.numpy(), onnx_estimate)
            assert np.allclose(torch_hidden_state, onnx_hidden_state, atol=1e-7), 'Failed to match hidden state1'
            assert np.allclose(torch_cell_state, onnx_cell_state, atol=1e-7), 'Failed to match cell state!'
        
        assert np.allclose(torch_hidden_state, final_hidden_state, atol=1e-7), 'Failed to match final hidden state!'
        assert np.allclose(torch_cell_state, final_cell_state, atol=1e-7), 'Failed to match final cell state!'
        # print("Torch and Onnx models outputs have been verified successfully!")

def evaluate(onnx_path):
    ort_session = ort.InferenceSession(onnx_path)

    every_call_mse = []
    every_call_accuracy = []
    for f_path in tqdm(small_evaluation_datasets, desc="Evaluating"):
        with open(f_path, 'r') as file:
            call_data = json.load(file)
        
        observations = np.asarray(call_data['observations'], dtype=np.float32)
        true_capacity = np.asarray(call_data['true_capacity'], dtype=np.float32)

        model_predictions = []
        hidden_state, cell_state = np.zeros((1, 1), dtype=np.float32), np.zeros((1, 1), dtype=np.float32)    
        for t in range(observations.shape[0]):
            obss = observations[t:t+1,:].reshape(1,1,-1)
            feed_dict = {'obs': obss,
                        'hidden_states': hidden_state,
                        'cell_states': cell_state
                        }
            bw_prediction, hidden_state, cell_state = ort_session.run(None, feed_dict)
            model_predictions.append(bw_prediction[0,0,0])
        # mse and accuracy of this call
        model_predictions = np.asarray(model_predictions, dtype=np.float32)
        true_capacity = true_capacity / 1e6
        model_predictions = model_predictions / 1e6
        call_mse = []
        call_accuracy = []
        for true_bw, pre_bw in zip(true_capacity, model_predictions):
            if np.isnan(true_bw) or np.isnan(pre_bw):
                continue
            else:
                mse_ = (true_bw - pre_bw) ** 2
                call_mse.append(mse_)
                accuracy_ = max(0, 1 - abs(pre_bw - true_bw) / true_bw)
                call_accuracy.append(accuracy_)
        call_mse = np.asarray(call_mse, dtype=np.float32)
        every_call_mse.append(np.mean(call_mse))
        call_accuracy = np.asarray(call_accuracy,  dtype=np.float32)
        every_call_accuracy.append(np.mean(call_accuracy))
    every_call_mse = np.asarray(every_call_mse, dtype=np.float32)
    every_call_accuracy = np.asarray(every_call_accuracy, dtype=np.float32)
    return np.mean(every_call_mse), np.mean(every_call_accuracy)
    

@pyrallis.wrap()
def train(config: TrainConfig):
    state_dim = STATE_DIM
    action_dim = ACTION_DIM
    train_policy_loss = []

    testdataset_file = open(pickle_path, 'rb')
    dataset = pickle.load(testdataset_file)
    print('dataset loaded')

    replay_buffer = ReplayBuffer(
        state_dim,
        action_dim,
        config.buffer_size,
        # Keep the large replay arrays on CPU and move sampled batches only.
        reward_mode=config.reward_mode,
        source_reward_lambda=config.source_reward_lambda,
        reward_lambda=config.reward_lambda,
        reward_error_cap=config.reward_error_cap,
    )
    replay_buffer.load_dataset(dataset)

    max_action = MAX_ACTION

    if config.checkpoints_path is not None:
        print(f"Checkpoints path: {config.checkpoints_path}")
        os.makedirs(config.checkpoints_path, exist_ok=True)
        with open(os.path.join(config.checkpoints_path, "config.yaml"), "w") as f:
            pyrallis.dump(config, f)

    # Set seeds
    seed = config.seed
    set_seed(seed)

    q_network = TwinQ(state_dim, action_dim).to(config.device)
    v_network = ValueFunction(state_dim).to(config.device)
    actor = (
        DeterministicPolicy(
            state_dim, action_dim, max_action, dropout=config.actor_dropout
        )
        if config.iql_deterministic
        else bwe_agent(
            max_action, state_dim, action_dim, config.device
        )
    )
    v_optimizer = torch.optim.Adam(v_network.parameters(), lr=config.vf_lr)
    q_optimizer = torch.optim.Adam(q_network.parameters(), lr=config.qf_lr)
    actor_optimizer = torch.optim.Adam(actor.parameters(), lr=config.actor_lr)

    kwargs = {
        "max_action": max_action,
        "actor": actor,
        "actor_optimizer": actor_optimizer,
        "q_network": q_network,
        "q_optimizer": q_optimizer,
        "v_network": v_network,
        "v_optimizer": v_optimizer,
        "discount": config.discount,
        "tau": config.tau,
        "device": config.device,
        # IQL
        "beta": config.beta,
        "iql_tau": config.iql_tau,
        "max_steps": config.max_timesteps,
        "capacity_aux_weight": config.capacity_aux_weight,
        "capacity_huber_delta": config.capacity_huber_delta,
    }

    print("---------------------------------------")
    print(f"Training IQL, Env: {config.env}, Seed: {seed}")
    print("---------------------------------------")

    # Initialize actor
    trainer = ImplicitQLearning(**kwargs)

    if config.load_model != "":
        policy_file = Path(config.load_model)
        trainer.load_state_dict(torch.load(policy_file))
        actor = trainer.actor

    if USE_WANDB:
        wandb_init(asdict(config))

    default_tensor_type = torch.get_default_dtype()

    for t in range(int(config.max_timesteps)):
        batch = replay_buffer.sample(config.batch_size)
        batch = [b.to(config.device) for b in batch]
        log_dict, policy_loss = trainer.train(batch)
        train_policy_loss.append(policy_loss)
        if USE_WANDB:
            wandb.log(log_dict, step=trainer.total_it)
        # Evaluate episode
        if (t + 1) % config.eval_freq == 0:
            print(f"Time steps: {t + 1}, Finish time: {datetime.datetime.now()}")

            pt_path = os.path.join(config.checkpoints_path, f"checkpoint_{t + 1}.pt")
            # onnx_path = os.path.join(config.checkpoints_path, f"checkpoint_{t + 1}.onnx")
            # save pt
            if config.checkpoints_path is not None:
                torch.save(trainer.state_dict()["actor"], pt_path)
            # save onnx
            # export2onnx(pt_path, onnx_path)
            # evaluate
            # mse_, accuracy_ = evaluate(onnx_path)
            if trainer.total_it > 1000:
                # print(f"MSE: {mse_}, Accuracy: {accuracy_}")
                print(f"average_loss: {sum(train_policy_loss) / len(train_policy_loss)}")
                train_policy_loss = []


if __name__ == "__main__":
    train()
