#!/usr/bin/env python3
"""
Test script to verify the fuzzy law matching fix.
This validates that corrected law numbers are no longer flagged as missing.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, '/Users/nicholasjacob/Documents/Aplicativos/Iudex')

from auto_fix_apostilas import find_similar_law_in_set, _edit_distance

def test_edit_distance():
    """Test the Levenshtein distance calculation."""
    print("Testing edit distance calculation...")
    
    tests = [
        ("11455", "11445", 1),  # Single digit change
        ("13467", "13465", 1),  # Single digit change
        ("3874", "13874", 2),   # Prefix addition
        ("8666", "8666", 0),    # Exact match
        ("12345", "54321", 5),  # Completely different
    ]
    
    passed = 0
    for s1, s2, expected in tests:
        result = _edit_distance(s1, s2)
        status = "✅" if result == expected else "❌"
        print(f"  {status} distance('{s1}', '{s2}') = {result} (expected {expected})")
        if result == expected:
            passed += 1
    
    print(f"Passed {passed}/{len(tests)} edit distance tests\n")
    return passed == len(tests)


def test_find_similar_law():
    """Test the fuzzy law matching function."""
    print("Testing fuzzy law matching...")
    
    fmt_refs = {"11445", "13465", "13874", "8666", "6766"}
    
    tests = [
        # (raw_number, expected_match, description)
        ("11455", "11445", "Single digit typo (transcription error)"),
        ("13467", "13465", "Digit confusion (13467 is Reforma Trabalhista, 13465 is REURB)"),
        ("3874", "13874", "Missing prefix (3874 → 13874, Lei de Liberdade Econômica)"),
        ("8666", "8666", "Exact match should still work"),
        ("9999", None, "Completely different number should return None"),
        ("12345", None, "Non-existent law should return None"),
    ]
    
    passed = 0
    for raw, expected, description in tests:
        result = find_similar_law_in_set(raw, fmt_refs)
        match = result == expected
        status = "✅" if match else "❌"
        
        result_str = result if result else "None"
        expected_str = expected if expected else "None"
        print(f"  {status} {description}")
        print(f"      Raw: {raw} → Match: {result_str} (expected {expected_str})")
        
        if match:
            passed += 1
    
    print(f"Passed {passed}/{len(tests)} fuzzy matching tests\n")
    return passed == len(tests)


def test_real_world_case():
    """Test the exact case from the bug report."""
    print("Testing real-world case from job 8743c693...")
    
    # Simulate the exact scenario from the audit
    raw_laws = {"11455", "13467", "3874"}  # Numbers found in RAW (transcription errors)
    fmt_laws = {"11445", "13465", "13874"}  # Correct numbers in formatted MD
    
    # Old logic (simple set difference) would produce false positives
    old_missing = raw_laws - fmt_laws
    print(f"  OLD LOGIC (set difference): {len(old_missing)} false positives")
    print(f"    Would flag as missing: {old_missing}")
    
    # New logic (fuzzy matching)
    new_missing = []
    corrections = []
    for raw_law in raw_laws:
        if raw_law in fmt_laws:
            continue
        
        similar = find_similar_law_in_set(raw_law, fmt_laws)
        if similar:
            corrections.append((raw_law, similar))
            continue
        
        new_missing.append(raw_law)
    
    print(f"  NEW LOGIC (fuzzy matching): {len(new_missing)} false positives")
    print(f"    Detected corrections: {corrections}")
    print(f"    Truly missing: {new_missing}")
    
    success = len(new_missing) == 0 and len(corrections) == 3
    status = "✅" if success else "❌"
    print(f"  {status} Result: {'All corrections detected correctly!' if success else 'FAILED'}\n")
    
    return success


def main():
    print("=" * 70)
    print("FUZZY LAW MATCHING - TEST SUITE")
    print("=" * 70)
    print()
    
    results = []
    
    # Run all tests
    results.append(("Edit Distance", test_edit_distance()))
    results.append(("Fuzzy Matching", test_find_similar_law()))
    results.append(("Real-world Case", test_real_world_case()))
    
    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print()
    print(f"Overall: {passed}/{total} test suites passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The fix is working correctly.")
        print("False positives for law corrections should now be eliminated.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Review the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
