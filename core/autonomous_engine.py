"""
Autonomous Decision Engine - Core Intelligence Layer

This module implements the Observe → Reason → Act → Evaluate loop
using Reinforcement Learning and adaptive algorithms.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import torch
import torch.nn as nn
from collections import deque
import json

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of autonomous actions the system can take"""
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    REBALANCE = "rebalance"
    ADJUST_PRICING = "adjust_pricing"
    MIGRATE_JOB = "migrate_job"
    RESTART_NODE = "restart_node"
    UPDATE_POLICY = "update_policy"
    NO_ACTION = "no_action"


@dataclass
class SystemState:
    """Current state of the GPU cloud system"""
    timestamp: datetime
    
    # Resource metrics
    total_gpus: int
    available_gpus: int
    gpu_utilization: float  # 0.0 to 1.0
    gpu_memory_usage: float
    gpu_temperature: Dict[str, float]
    
    # Job metrics
    queue_depth: int
    active_jobs: int
    completed_jobs_1h: int
    failed_jobs_1h: int
    avg_job_duration: float
    p95_job_latency: float
    
    # Cost metrics
    current_cost_per_hour: float
    revenue_per_hour: float
    profit_margin: float
    
    # Market metrics
    competitor_pricing: Dict[str, float]
    demand_forecast_1h: float
    demand_forecast_24h: float
    
    # Health metrics
    node_health_scores: Dict[str, float]
    error_rate: float
    sla_compliance: float
    
    # User behavior
    active_users: int
    new_user_signups_1h: int
    user_satisfaction_score: float
    
    def to_tensor(self) -> torch.Tensor:
        """Convert state to tensor for neural network input"""
        features = [
            self.gpu_utilization,
            self.gpu_memory_usage,
            self.queue_depth / 100.0,  # Normalize
            self.active_jobs / 50.0,
            self.error_rate,
            self.sla_compliance,
            self.profit_margin,
            self.demand_forecast_1h / 100.0,
            self.user_satisfaction_score,
            min(self.avg_job_duration / 3600.0, 1.0),  # Cap at 1 hour
        ]
        return torch.tensor(features, dtype=torch.float32)


@dataclass
class Action:
    """Action to be taken by the autonomous system"""
    action_type: ActionType
    parameters: Dict[str, Any]
    confidence: float
    expected_impact: Dict[str, float]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Observation:
    """Observation from the environment after taking an action"""
    state: SystemState
    reward: float
    done: bool
    info: Dict[str, Any]


class ActorCriticNetwork(nn.Module):
    """
    Actor-Critic neural network for reinforcement learning.
    Actor outputs action probabilities, Critic estimates state value.
    """
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 256):
        super().__init__()
        
        # Shared feature extractor
        self.shared = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        
        # Actor head (policy)
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, action_dim),
            nn.Softmax(dim=-1)
        )
        
        # Critic head (value function)
        self.critic = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )
        
    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass returning action probabilities and state value"""
        features = self.shared(state)
        action_probs = self.actor(features)
        state_value = self.critic(features)
        return action_probs, state_value


class ReinforcementLearningAgent:
    """
    Reinforcement Learning agent using Proximal Policy Optimization (PPO)
    for continuous learning and decision making.
    """
    
    def __init__(
        self,
        state_dim: int = 10,
        action_dim: int = 8,
        learning_rate: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_epsilon: float = 0.2,
        entropy_coef: float = 0.01,
        value_coef: float = 0.5,
    ):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        self.network = ActorCriticNetwork(state_dim, action_dim).to(self.device)
        self.optimizer = torch.optim.Adam(self.network.parameters(), lr=learning_rate)
        
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_epsilon = clip_epsilon
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        
        # Experience buffer
        self.states = []
        self.actions = []
        self.rewards = []
        self.values = []
        self.log_probs = []
        self.dones = []
        
        # Metrics
        self.episode_rewards = deque(maxlen=100)
        self.training_steps = 0
        
    def select_action(self, state: SystemState) -> Tuple[ActionType, float]:
        """Select action based on current policy"""
        state_tensor = state.to_tensor().unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            action_probs, state_value = self.network(state_tensor)
        
        # Sample action from probability distribution
        action_dist = torch.distributions.Categorical(action_probs)
        action_idx = action_dist.sample()
        log_prob = action_dist.log_prob(action_idx)
        
        # Store for training
        self.states.append(state_tensor)
        self.actions.append(action_idx)
        self.values.append(state_value)
        self.log_probs.append(log_prob)
        
        action_type = list(ActionType)[action_idx.item()]
        confidence = action_probs[0, action_idx].item()
        
        return action_type, confidence
    
    def store_transition(self, reward: float, done: bool):
        """Store transition for training"""
        self.rewards.append(reward)
        self.dones.append(done)
    
    def compute_gae(self, next_value: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Compute Generalized Advantage Estimation"""
        advantages = []
        gae = 0
        
        values = self.values + [next_value]
        
        for t in reversed(range(len(self.rewards))):
            delta = self.rewards[t] + self.gamma * values[t + 1] * (1 - self.dones[t]) - values[t]
            gae = delta + self.gamma * self.gae_lambda * (1 - self.dones[t]) * gae
            advantages.insert(0, gae)
        
        advantages = torch.tensor(advantages, device=self.device)
        returns = advantages + torch.cat(self.values)
        
        return advantages, returns
    
    def update_policy(self, next_state: SystemState):
        """Update policy using PPO algorithm"""
        if len(self.states) == 0:
            return
        
        next_state_tensor = next_state.to_tensor().unsqueeze(0).to(self.device)
        with torch.no_grad():
            _, next_value = self.network(next_state_tensor)
        
        advantages, returns = self.compute_gae(next_value)
        
        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        # Convert lists to tensors
        states = torch.cat(self.states)
        actions = torch.stack(self.actions)
        old_log_probs = torch.stack(self.log_probs)
        
        # PPO update
        for _ in range(4):  # Multiple epochs
            action_probs, state_values = self.network(states)
            action_dist = torch.distributions.Categorical(action_probs)
            
            new_log_probs = action_dist.log_prob(actions)
            entropy = action_dist.entropy().mean()
            
            # Compute ratio and clipped surrogate objective
            ratio = torch.exp(new_log_probs - old_log_probs)
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * advantages
            
            actor_loss = -torch.min(surr1, surr2).mean()
            critic_loss = nn.MSELoss()(state_values.squeeze(), returns)
            
            loss = actor_loss + self.value_coef * critic_loss - self.entropy_coef * entropy
            
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.network.parameters(), 0.5)
            self.optimizer.step()
        
        # Clear buffers
        self.states.clear()
        self.actions.clear()
        self.rewards.clear()
        self.values.clear()
        self.log_probs.clear()
        self.dones.clear()
        
        self.training_steps += 1
        
        logger.info(f"Policy updated. Training step: {self.training_steps}, Loss: {loss.item():.4f}")
    
    def save_checkpoint(self, path: str):
        """Save model checkpoint"""
        torch.save({
            'network_state_dict': self.network.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'training_steps': self.training_steps,
        }, path)
        logger.info(f"Checkpoint saved to {path}")
    
    def load_checkpoint(self, path: str):
        """Load model checkpoint"""
        checkpoint = torch.load(path, map_location=self.device)
        self.network.load_state_dict(checkpoint['network_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.training_steps = checkpoint['training_steps']
        logger.info(f"Checkpoint loaded from {path}")


class RewardCalculator:
    """
    Calculate reward signals for reinforcement learning based on
    multiple objectives: cost, latency, reliability, user satisfaction.
    """
    
    def __init__(
        self,
        cost_weight: float = 0.3,
        latency_weight: float = 0.3,
        reliability_weight: float = 0.2,
        satisfaction_weight: float = 0.2,
    ):
        self.cost_weight = cost_weight
        self.latency_weight = latency_weight
        self.reliability_weight = reliability_weight
        self.satisfaction_weight = satisfaction_weight
        
        # Baseline metrics for normalization
        self.baseline_cost = 100.0
        self.baseline_latency = 10.0
        self.baseline_reliability = 0.99
        self.baseline_satisfaction = 0.8
    
    def calculate_reward(
        self,
        prev_state: SystemState,
        action: Action,
        new_state: SystemState,
    ) -> float:
        """
        Calculate reward based on state transition.
        Positive reward for improvements, negative for degradation.
        """
        
        # Cost efficiency reward (lower is better)
        cost_delta = (prev_state.current_cost_per_hour - new_state.current_cost_per_hour) / self.baseline_cost
        cost_reward = self.cost_weight * cost_delta
        
        # Latency reward (lower is better)
        latency_delta = (prev_state.p95_job_latency - new_state.p95_job_latency) / self.baseline_latency
        latency_reward = self.latency_weight * latency_delta
        
        # Reliability reward (higher is better)
        reliability_delta = (new_state.sla_compliance - prev_state.sla_compliance) / (1 - self.baseline_reliability)
        reliability_reward = self.reliability_weight * reliability_delta
        
        # User satisfaction reward (higher is better)
        satisfaction_delta = (new_state.user_satisfaction_score - prev_state.user_satisfaction_score) / (1 - self.baseline_satisfaction)
        satisfaction_reward = self.satisfaction_weight * satisfaction_delta
        
        # Penalty for high error rate
        error_penalty = -2.0 * new_state.error_rate if new_state.error_rate > 0.01 else 0.0
        
        # Bonus for high GPU utilization (but not overloaded)
        utilization_bonus = 0.0
        if 0.8 <= new_state.gpu_utilization <= 0.95:
            utilization_bonus = 0.5
        elif new_state.gpu_utilization > 0.95:
            utilization_bonus = -0.5  # Penalty for overload
        
        total_reward = (
            cost_reward +
            latency_reward +
            reliability_reward +
            satisfaction_reward +
            error_penalty +
            utilization_bonus
        )
        
        logger.debug(
            f"Reward breakdown - Cost: {cost_reward:.3f}, Latency: {latency_reward:.3f}, "
            f"Reliability: {reliability_reward:.3f}, Satisfaction: {satisfaction_reward:.3f}, "
            f"Total: {total_reward:.3f}"
        )
        
        return total_reward


class AutonomousDecisionEngine:
    """
    Main autonomous decision engine implementing the ORAE loop:
    Observe → Reason → Act → Evaluate
    """
    
    def __init__(self):
        self.rl_agent = ReinforcementLearningAgent()
        self.reward_calculator = RewardCalculator()
        
        self.current_state: Optional[SystemState] = None
        self.previous_state: Optional[SystemState] = None
        self.last_action: Optional[Action] = None
        
        self.decision_history = deque(maxlen=1000)
        self.running = False
        
        logger.info("Autonomous Decision Engine initialized")
    
    async def observe(self) -> SystemState:
        """
        OBSERVE: Collect telemetry and system metrics
        """
        # This would integrate with actual monitoring systems
        # For now, we'll create a placeholder that would be replaced with real data
        
        from .telemetry import TelemetryCollector
        collector = TelemetryCollector()
        
        state = await collector.collect_system_state()
        
        logger.debug(f"Observed state: GPU util={state.gpu_utilization:.2%}, Queue={state.queue_depth}")
        
        return state
    
    def reason(self, state: SystemState) -> Action:
        """
        REASON: Use RL agent to decide on best action
        """
        action_type, confidence = self.rl_agent.select_action(state)
        
        # Generate action parameters based on action type
        parameters = self._generate_action_parameters(action_type, state)
        
        # Estimate expected impact
        expected_impact = self._estimate_impact(action_type, parameters, state)
        
        action = Action(
            action_type=action_type,
            parameters=parameters,
            confidence=confidence,
            expected_impact=expected_impact,
        )
        
        logger.info(
            f"Reasoned action: {action_type.value} with confidence {confidence:.2%}, "
            f"Expected impact: {expected_impact}"
        )
        
        return action
    
    async def act(self, action: Action) -> bool:
        """
        ACT: Execute the decided action
        """
        try:
            from .executor import ActionExecutor
            executor = ActionExecutor()
            
            success = await executor.execute(action)
            
            if success:
                logger.info(f"Successfully executed action: {action.action_type.value}")
            else:
                logger.warning(f"Failed to execute action: {action.action_type.value}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error executing action: {e}", exc_info=True)
            return False
    
    def evaluate(self, prev_state: SystemState, action: Action, new_state: SystemState):
        """
        EVALUATE: Calculate reward and update RL policy
        """
        reward = self.reward_calculator.calculate_reward(prev_state, action, new_state)
        
        # Store transition
        self.rl_agent.store_transition(reward, done=False)
        
        # Periodically update policy (every 10 decisions)
        if len(self.rl_agent.rewards) >= 10:
            self.rl_agent.update_policy(new_state)
        
        # Record decision
        self.decision_history.append({
            'timestamp': datetime.now().isoformat(),
            'action': action.action_type.value,
            'parameters': action.parameters,
            'reward': reward,
            'confidence': action.confidence,
            'gpu_utilization': new_state.gpu_utilization,
            'queue_depth': new_state.queue_depth,
        })
        
        logger.info(f"Evaluated action with reward: {reward:.3f}")
    
    async def run_decision_loop(self, interval_seconds: int = 60):
        """
        Main autonomous decision loop running continuously
        """
        self.running = True
        logger.info(f"Starting autonomous decision loop (interval: {interval_seconds}s)")
        
        while self.running:
            try:
                # OBSERVE
                current_state = await self.observe()
                
                # REASON
                action = self.reason(current_state)
                
                # ACT
                action_success = await self.act(action)
                
                # Wait for action to take effect
                await asyncio.sleep(10)
                
                # OBSERVE again to see the effect
                new_state = await self.observe()
                
                # EVALUATE
                if self.previous_state is not None and action_success:
                    self.evaluate(self.previous_state, action, new_state)
                
                # Update state tracking
                self.previous_state = current_state
                self.current_state = new_state
                self.last_action = action
                
                # Save checkpoint periodically
                if self.rl_agent.training_steps % 100 == 0:
                    self.rl_agent.save_checkpoint(f"checkpoints/rl_agent_step_{self.rl_agent.training_steps}.pt")
                
                # Wait for next iteration
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in decision loop: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)
    
    def stop(self):
        """Stop the autonomous decision loop"""
        self.running = False
        logger.info("Stopping autonomous decision loop")
    
    def _generate_action_parameters(self, action_type: ActionType, state: SystemState) -> Dict[str, Any]:
        """Generate appropriate parameters for each action type"""
        if action_type == ActionType.SCALE_UP:
            # Calculate how many GPUs to add
            demand_ratio = state.queue_depth / max(state.active_jobs, 1)
            gpu_count = min(int(demand_ratio * 2), 10)
            return {'gpu_count': gpu_count, 'gpu_type': 'A100'}
        
        elif action_type == ActionType.SCALE_DOWN:
            # Calculate how many GPUs to remove
            excess_capacity = state.available_gpus - state.queue_depth
            gpu_count = max(int(excess_capacity * 0.5), 1)
            return {'gpu_count': gpu_count}
        
        elif action_type == ActionType.ADJUST_PRICING:
            # Adjust pricing based on utilization and competition
            if state.gpu_utilization > 0.9:
                price_multiplier = 1.1  # Increase price when busy
            elif state.gpu_utilization < 0.5:
                price_multiplier = 0.9  # Decrease price when idle
            else:
                price_multiplier = 1.0
            return {'price_multiplier': price_multiplier}
        
        elif action_type == ActionType.MIGRATE_JOB:
            # Find unhealthy nodes and target healthy ones
            unhealthy_nodes = [node for node, score in state.node_health_scores.items() if score < 0.8]
            healthy_nodes = [node for node, score in state.node_health_scores.items() if score > 0.9]
            return {'source_nodes': unhealthy_nodes[:3], 'target_nodes': healthy_nodes[:3]}
        
        else:
            return {}
    
    def _estimate_impact(self, action_type: ActionType, parameters: Dict[str, Any], state: SystemState) -> Dict[str, float]:
        """Estimate the expected impact of an action"""
        impact = {
            'cost_delta': 0.0,
            'latency_delta': 0.0,
            'utilization_delta': 0.0,
            'reliability_delta': 0.0,
        }
        
        if action_type == ActionType.SCALE_UP:
            gpu_count = parameters.get('gpu_count', 0)
            impact['cost_delta'] = gpu_count * 2.5  # $2.5/hr per GPU
            impact['latency_delta'] = -0.2  # Reduce latency
            impact['utilization_delta'] = -0.1  # Lower utilization
        
        elif action_type == ActionType.SCALE_DOWN:
            gpu_count = parameters.get('gpu_count', 0)
            impact['cost_delta'] = -gpu_count * 2.5
            impact['utilization_delta'] = 0.1  # Higher utilization
        
        elif action_type == ActionType.MIGRATE_JOB:
            impact['reliability_delta'] = 0.05  # Improve reliability
            impact['latency_delta'] = 0.1  # Slight latency increase during migration
        
        return impact
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics and performance statistics"""
        recent_decisions = list(self.decision_history)[-100:]
        
        if not recent_decisions:
            return {'status': 'no_data'}
        
        avg_reward = np.mean([d['reward'] for d in recent_decisions])
        action_distribution = {}
        for d in recent_decisions:
            action = d['action']
            action_distribution[action] = action_distribution.get(action, 0) + 1
        
        return {
            'status': 'running' if self.running else 'stopped',
            'training_steps': self.rl_agent.training_steps,
            'total_decisions': len(self.decision_history),
            'avg_reward_100': avg_reward,
            'action_distribution': action_distribution,
            'current_state': {
                'gpu_utilization': self.current_state.gpu_utilization if self.current_state else None,
                'queue_depth': self.current_state.queue_depth if self.current_state else None,
                'sla_compliance': self.current_state.sla_compliance if self.current_state else None,
            },
            'last_action': self.last_action.action_type.value if self.last_action else None,
        }


# Singleton instance
_engine_instance: Optional[AutonomousDecisionEngine] = None


def get_decision_engine() -> AutonomousDecisionEngine:
    """Get or create the singleton decision engine instance"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = AutonomousDecisionEngine()
    return _engine_instance
