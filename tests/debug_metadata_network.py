import time
import socket
import ssl
from urllib.parse import urlencode
import sys

def print_timeout_exception(milestone, url, raw_params, elapsed):
    print("\n" + "="*80)
    print("!!! CUSTOM TIMEOUT EXCEPTION TRIGGERED !!!")
    print("="*80)
    print(f"Failed at Milestone: {milestone}")
    print(f"Time Elapsed:        {elapsed:.4f} seconds (Threshold > 4.0s)")
    print(f"Exact URL:           {url}")
    print(f"Raw Parameters:      {raw_params}")
    print(f"Socket State:        HUNG / UNRESPONSIVE")
    print("="*80 + "\n")
    raise TimeoutError(f"Network hung at {milestone} after {elapsed:.4f}s")

def run_probe():
    target = 'WASP-12 b'
    
    print(f"Starting Diagnostic Probe for target: '{target}'\n")
    
    host = 'exoplanetarchive.ipac.caltech.edu'
    port = 443
    path = '/TAP/sync'
    
    select_cols = "pl_name, pl_orbper, pl_orbpererr1, st_rad, st_raderr1, st_lum, st_teff, st_mass, sy_jmag, pl_trandep, pl_ratror"
    query = f"SELECT {select_cols} FROM pscomppars WHERE pl_name = '{target}'"
    
    params = {
        'query': query,
        'format': 'csv'
    }
    encoded_params = urlencode(params)
    url = f"https://{host}{path}"
    
    # =========================================================================
    # Milestone 1: DNS Resolution & Target Name Sanitization Connection
    # =========================================================================
    t0 = time.perf_counter()
    try:
        ip = socket.gethostbyname(host)
        sock = socket.create_connection((ip, port), timeout=4.0)
        context = ssl.create_default_context()
        ssock = context.wrap_socket(sock, server_hostname=host)
        # Apply strict 4.0 second timeout to all blocking operations
        ssock.settimeout(4.0)
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print_timeout_exception("Milestone 1: DNS & Connection", url, params, elapsed)
            
    ms1_time = time.perf_counter() - t0
    print(f"[Milestone 1] DNS Resolution & Connection: {ms1_time:.4f}s")
    if ms1_time > 4.0:
        print_timeout_exception("Milestone 1: DNS & Connection", url, params, ms1_time)

    # =========================================================================
    # Milestone 2: Request Payload Delivery to Remote URL
    # =========================================================================
    request_str = (
        f"POST {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(encoded_params)}\r\n"
        f"Connection: close\r\n\r\n"
        f"{encoded_params}"
    )
    
    t2_start = time.perf_counter()
    try:
        ssock.sendall(request_str.encode('utf-8'))
    except Exception as e:
        elapsed = time.perf_counter() - t2_start
        print_timeout_exception("Milestone 2: Payload Delivery", url, params, elapsed)
            
    ms2_time = time.perf_counter() - t2_start
    print(f"[Milestone 2] Payload Delivery: {ms2_time:.4f}s")
    if ms2_time > 4.0:
        print_timeout_exception("Milestone 2: Payload Delivery", url, params, ms2_time)

    # =========================================================================
    # Milestone 3: Server Handshake / Processing Waiting Time (TTFB)
    # =========================================================================
    t3_start = time.perf_counter()
    try:
        first_byte = ssock.recv(1)
        if not first_byte:
            raise ConnectionError("Connection closed before receiving data.")
    except Exception as e:
        elapsed = time.perf_counter() - t3_start
        print_timeout_exception("Milestone 3: TTFB", url, params, elapsed)
            
    ms3_time = time.perf_counter() - t3_start
    print(f"[Milestone 3] Server Handshake / TTFB: {ms3_time:.4f}s")
    if ms3_time > 4.0:
        print_timeout_exception("Milestone 3: TTFB", url, params, ms3_time)

    # =========================================================================
    # Milestone 4: Binary Data Stream Ingestion and Parsing
    # =========================================================================
    t4_start = time.perf_counter()
    chunks = [first_byte]
    try:
        while True:
            # We are using a 4.0s timeout per read operation
            chunk = ssock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            
            total_elapsed = time.perf_counter() - t4_start
            if total_elapsed > 4.0:
                print_timeout_exception("Milestone 4: Data Stream Ingestion", url, params, total_elapsed)
    except Exception as e:
        elapsed = time.perf_counter() - t4_start
        print_timeout_exception("Milestone 4: Data Stream Ingestion", url, params, elapsed)
            
    ms4_time = time.perf_counter() - t4_start
    full_data = b"".join(chunks)
    payload_size = len(full_data)
    
    print(f"[Milestone 4] Data Stream Ingestion: {ms4_time:.4f}s")
    if ms4_time > 4.0:
        print_timeout_exception("Milestone 4: Data Stream Ingestion", url, params, ms4_time)
        
    print(f"\nTotal Payload Size: {payload_size} bytes")
    
    # Try parsing just to verify it's a valid CSV and not a huge HTML error or composite table dump
    try:
        # Split headers
        header_end = full_data.find(b"\r\n\r\n") + 4
        if header_end < 4:
            header_end = full_data.find(b"\n\n") + 2
        body = full_data[header_end:].decode('utf-8')
        lines = body.strip().split('\n')
        print(f"Extracted CSV Rows: {len(lines)}")
        if len(lines) > 0:
            print(f"Sample data preview: {lines[-1]}")
    except Exception as e:
        print(f"Failed to parse body: {e}")

    # =========================================================================
    # Final Diagnosis Summary
    # =========================================================================
    print("\n" + "="*80)
    print("=== SUMMARY OF FINDINGS ===")
    print("="*80)
    
    if payload_size > 1000000:
        print("DIAGNOSIS: Accidental multi-megabyte composite table download.")
        print("Root Cause: The query lacked proper limits or indexing, causing the server ")
        print("to return a massive unindexed payload.")
    else:
        print("DIAGNOSIS: Network probe completed successfully without hanging.")
        print("The NASA Exoplanet Archive TAP endpoint is responsive.")
        print("Payload size is normal and parsing did not trigger timeouts.")
        print("If the original pipeline hangs, it may be due to an unhandled exception")
        print("elsewhere, or Astroquery internally downloading extra metadata not replicated here.")
    print("="*80 + "\n")

if __name__ == '__main__':
    try:
        run_probe()
    except TimeoutError:
        sys.exit(1)
