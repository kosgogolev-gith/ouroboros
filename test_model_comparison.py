#!/usr/bin/env python3
"""
Test script to compare Claude Haiku 5.5 vs nemotron-3.5-lightning:free
"""
import time
import sys
import os

# Add the repo root to path so we can import ouroboros package
sys.path.insert(0, '/home/goga/ouroboros_repo')

from ouroboros.llm import LLMClient

def test_model(model_id, prompt_text):
    """Test a single model with a prompt, return metrics."""
    client = LLMClient()
    messages = [{"role": "user", "content": prompt_text}]
    
    start = time.time()
    try:
        response, usage = client.chat(
            messages=messages,
            model=model_id,
            max_tokens=1024,
            reasoning_effort="medium"
        )
        elapsed = time.time() - start
        
        # Extract metrics
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        cost = usage.get("cost", 0.0)
        
        # If cost not provided, calculate using known pricing (approximate)
        if cost == 0.0:
            # Use pricing from tech-radar as fallback
            pricing = {
                "anthropic/claude-haiku-5.5": (0.10, 0.50),  # input, output per 1M
                "nvidia/nemotron-3.5-lightning:free": (0.0, 0.0)
            }
            if model_id in pricing:
                input_price, output_price = pricing[model_id]
                cost = (prompt_tokens * input_price / 1_000_000) + (completion_tokens * output_price / 1_000_000)
        
        return {
            "success": True,
            "response": response.get("content", ""),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost": cost,
            "elapsed": elapsed,
            "error": None
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "success": False,
            "response": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0,
            "elapsed": elapsed,
            "error": str(e)
        }

def main():
    # Test prompts
    prompts = [
        ("simple query", "What is the capital of France?"),
        ("coding", "Write a Python function to calculate factorial of a number."),
        ("analysis", "Explain the difference between supervised and unsupervised learning in 2-3 sentences.")
    ]
    
    # Models to test
    models = [
        "nvidia/nemotron-3.5-lightning:free",
        "anthropic/claude-haiku-5.5"
    ]
    
    results = {}
    
    for model in models:
        print(f"\nTesting model: {model}")
        results[model] = {}
        for prompt_name, prompt_text in prompts:
            print(f"  Running: {prompt_name}")
            result = test_model(model, prompt_text)
            results[model][prompt_name] = result
            if result["success"]:
                print(f"    Success: {result['total_tokens']} tokens, ${result['cost']:.6f}, {result['elapsed']:.2f}s")
            else:
                print(f"    Failed: {result['error']}")
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for model in models:
        print(f"\nModel: {model}")
        for prompt_name in ["simple query", "coding", "analysis"]:
            res = results[model][prompt_name]
            if res["success"]:
                print(f"  {prompt_name:12}: {res['total_tokens']:4d} tokens, ${res['cost']:.6f}, {res['elapsed']:5.2f}s")
            else:
                print(f"  {prompt_name:12}: FAILED - {res['error']}")
    
    # Calculate averages
    print("\n" + "="*60)
    print("AVERAGES (across prompt types)")
    print("="*60)
    for model in models:
        tokens = []
        costs = []
        times = []
        for prompt_name in ["simple query", "coding", "analysis"]:
            res = results[model][prompt_name]
            if res["success"]:
                tokens.append(res["total_tokens"])
                costs.append(res["cost"])
                times.append(res["elapsed"])
        if tokens:
            avg_tokens = sum(tokens)/len(tokens)
            avg_cost = sum(costs)/len(costs)
            avg_time = sum(times)/len(times)
            print(f"{model:35} | {avg_tokens:6.1f} tok | ${avg_cost:.6f} | {avg_time:5.2f}s")
        else:
            print(f"{model:35} | All failed")

if __name__ == "__main__":
    main()