import json
import sys

logfile = r'C:\Users\MIT\.gemini\antigravity\brain\e27c796a-f44b-4c27-9264-cc5ca4aa33bd\.system_generated\tasks\task-151.log'
with open(logfile, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

parts = content.split('=== RESULTS ===\n')

print("=== LOG OUTPUT ===")
for line in parts[0].split('\n'):
    if '[Fallback]' in line or '[Orchestrator]' in line or 'Signal significance floor' in line:
        print(line)

if len(parts) > 1:
    results = json.loads(parts[1])
    print(f"\nTotal Candidates Found: {len(results)}")
    
    clean_results = []
    for i, r in enumerate(results):
        print(f"Candidate {i}: period={r['period_days']:.3f} days, snr={r['snr']:.2f}, status={r['vetting_status']}")
        r_clean = {k: v for k, v in r.items() if k not in ('periodogram', 'transit_model_flux', 'transit_model_time', 'lc_flux', 'lc_time', 'ttv_residuals', 'transit_model', 'ttv_data')}
        clean_results.append(r_clean)
        
    with open('final_payload.json', 'w') as f:
        json.dump(clean_results, f, indent=2)
