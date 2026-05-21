"""Subscription ingress: poll message bus → trigger_context → FlowRuntime.run."""

from flow_engine.runner.subscription.spec import SubscriptionSpec, load_subscription_spec

__all__ = ["SubscriptionSpec", "load_subscription_spec"]
