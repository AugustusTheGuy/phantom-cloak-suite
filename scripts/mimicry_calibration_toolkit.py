#!/usr/bin/env python3
"""
Mimicry Calibration Toolkit (v1)

Helps you tune Reality SNIs, Hysteria2 parameters, and AmneziaWG noise
to better match real residential traffic from the target country.

In production this would compare against reference captures.
"""

def main():
    print("=== Delphi Mimicry Calibration Toolkit ===")
    print("1. Capture real home traffic from someone in the target country (with consent).")
    print("2. Compare JA4+ fingerprints, packet sizes, and timing distributions.")
    print("3. Update the corresponding sing-box client config and server Reality settings.")
    print("\nCurrent best practice SNIs per location are stored in singbox_manager.py")

if __name__ == "__main__":
    main()