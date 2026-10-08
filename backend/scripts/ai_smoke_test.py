import asyncio
import argparse
import os
import sys
import httpx
from pathlib import Path
from dotenv import load_dotenv

# Ensure we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL
from app.services.column_understanding import analyse
import pandas as pd
import time

async def list_models():
    """Lists Gemini models using the configured API key."""
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is missing from environment.")
        return

    url = "https://generativelanguage.googleapis.com/v1beta/models"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={"x-goog-api-key": GEMINI_API_KEY})
            print(f"HTTP {response.status_code}")
            if response.status_code != 200:
                try:
                    data = response.json()
                    err = data.get("error", {})
                    print(f"Error [{err.get('code')}]: {err.get('status')} - {err.get('message')}")
                except:
                    print(f"Error: {response.text}")
                return

            models = response.json().get("models", [])
            print("Models supporting generateContent:")
            for m in models:
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    # just print the model name, strip models/ prefix if present
                    name = m["name"].replace("models/", "")
                    print(f" - {name}")
    except Exception as e:
        print(f"Connection error: {type(e).__name__} - {e}")

async def run_pipeline():
    """Runs the ambiguous headers through the pipeline."""
    csv_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ambiguous_headers.csv"
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        return

    df = pd.read_csv(csv_path)
    
    reports, timings, notice, reason_code = await analyse(df, ai_consent=True, file_id=None)
    
    print("\nColumns mapped:")
    for r in reports:
        print(f"{r['raw_column']:<15} -> {str(r['suggested_field']):<15} | Source: {r.get('source')} | Reason code / Notice: {reason_code if r.get('source') == 'fallback' else ''} / {notice if r.get('source') == 'fallback' else ''}")

    print(f"\nTimings:")
    print(f"  Tier 1: {timings.tier1_ms:.2f}ms")
    print(f"  Tier 2: {timings.tier2_ms:.2f}ms")
    print(f"  Total : {timings.total_ms:.2f}ms")
    if notice:
        print(f"Notice: {notice}")

async def benchmark_models():
    from app.services.tier1_classifier import classify_columns, ROUTE_GEMINI
    from app.services.tier2_gemini import describe_column, _ENDPOINT_TEMPLATE, GeminiVerdict
    
    csv_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ambiguous_headers.csv"
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        return
        
    df = pd.read_csv(csv_path)
    tier1_results = classify_columns(df, ai_available=True)
    ambiguous = [
        describe_column(df[col.raw_column], col.raw_column, col.label)
        for col in tier1_results 
        if col.route == ROUTE_GEMINI and col.canonical is None
    ]
    
    models_to_test = [GEMINI_MODEL, GEMINI_FALLBACK_MODEL]
    
    variants = {
        "(a) plain-text prompt without schema": {"mime": "text/plain", "schema": None, "prompt_suffix": ""},
        "(b) JSON mime type without schema": {"mime": "application/json", "schema": None, "prompt_suffix": " Return a JSON object."},
        "(c) with the schema": {"mime": "application/json", "schema": GeminiVerdict.model_json_schema(), "prompt_suffix": ""},
        "(e) smaller prompt": {"mime": "application/json", "schema": GeminiVerdict.model_json_schema(), "prompt_suffix": "", "small": True},
    }

    import json
    
    print("Benchmarking models:")
    async with httpx.AsyncClient(
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        timeout=15.0
    ) as client:
        for model in models_to_test:
            for variant_name, v_config in variants.items():
                print(f"\nModel: {model} | Variant: {variant_name}")
                for run in range(1, 4):
                    started = time.perf_counter()
                    try:
                        cols_to_send = ambiguous[:1] if v_config.get("small") else ambiguous
                        for c in cols_to_send:
                            if v_config.get("small"):
                                c["samples"] = c.get("samples", [])[:2] # Fewer samples

                        prompt = "Identify the business meaning of each column below.\n\nColumns:\n" + json.dumps(cols_to_send, indent=2) + v_config["prompt_suffix"]
                        prompt_len = len(prompt)
                        
                        payload = {
                            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                            "generationConfig": {
                                "responseMimeType": v_config["mime"],
                                "temperature": 0,
                            },
                        }
                        if v_config["schema"]:
                            payload["generationConfig"]["responseJsonSchema"] = v_config["schema"]
                            
                        url = _ENDPOINT_TEMPLATE.format(model=model)
                        resp = await client.post(url, json=payload)
                        elapsed = time.perf_counter() - started
                        
                        if resp.status_code == 200:
                            print(f"  Run {run}: HTTP 200, {elapsed:.2f}s | chars: {prompt_len}")
                        else:
                            print(f"  Run {run}: HTTP {resp.status_code}, {elapsed:.2f}s | chars: {prompt_len}")
                    except httpx.ReadTimeout:
                        elapsed = time.perf_counter() - started
                        print(f"  Run {run}: Error ReadTimeout, {elapsed:.2f}s | chars: {prompt_len}")
                    except Exception as e:
                        elapsed = time.perf_counter() - started
                        print(f"  Run {run}: Error {type(e).__name__} ({e}), {elapsed:.2f}s | chars: {prompt_len}")

if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()

    if args.list_models:
        asyncio.run(list_models())
    elif args.benchmark:
        asyncio.run(benchmark_models())
    else:
        asyncio.run(run_pipeline())
