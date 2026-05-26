import re

def sanitize_address(address: str) -> str:
    if not address or not isinstance(address, str):
        return address
    
    # Strip any leading/trailing spaces
    address = address.strip()
    
    # We want to match street numbers.
    # Refined pattern:
    # 1. Word boundary \b
    # 2. Negative lookahead to ensure the word starting with digits does NOT end with st, nd, rd, th (case-insensitive)
    # 3. Match the digits \d+
    # 4. Match any trailing parts of the street number like letters, dashes, slashes [-/\w]*
    # 5. Match the space \s+
    # 6. Followed by either:
    #    - A letter [a-zA-Z]
    #    - An ordinal number starting with digits (e.g. 1st, 2nd, 3rd, 16th)
    pattern = r'\b(?!\d+(?:st|nd|rd|th|ST|ND|RD|TH)\b)\d+[-/\w]*\s+(?=[a-zA-Z]|\d+(?:st|nd|rd|th|ST|ND|RD|TH)\b)'
    
    # Replace matches with empty string
    sanitized = re.sub(pattern, '', address)
    
    return sanitized

# Test cases
test_cases = [
    "123 N Main St, Denver, CO 80202",
    "9900 E 40th Ave, Denver, CO",
    "Starbucks, 1401 Broadway, Denver, CO 80202",
    "McDonald's - 456 E 17th Ave, Denver, CO",
    "12345 Road 24, Fort Morgan, CO",
    "Home",
    "Unknown",
    "123-A West 5th St, Austin, TX",
    "123-1/2 Broadway, New York, NY",
    "7-Eleven, 888 N Lincoln St, Denver, CO 80203",
    "888 Lincoln St, Denver, CO 80203",
    "1234 16th Street Mall, Denver, CO 80202",
    "Starbucks 1401 Broadway", # No comma/dash business name
    "Target 555 Broadway, Denver, CO",
    "101 1st Ave, Denver, CO",
    "303 3rd St, Denver, CO",
    "202 2nd St, Denver, CO",
    "404 4th St, Denver, CO",
]

print("REFINED PII ADDRESS SANITIZATION TEST (FIXED ORDINAL STREET NAMES FOLLOWED):")
for case in test_cases:
    sanitized = sanitize_address(case)
    print(f"Original:  {case}")
    print(f"Sanitized: {sanitized}")
    print("-" * 50)
