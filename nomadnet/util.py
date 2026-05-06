import re
import unicodedata

invalid_rendering = ["🕵️", "☝"]

# Unicode blocks to strip (symbols, dingbats, emoji ranges)
STRIP_BLOCKS_RE = re.compile(
    '['
    '\U0001F600-\U0001F64F'  # Emoticons
    '\U0001F300-\U0001F5FF'  # Misc Symbols & Pictographs
    '\U0001F680-\U0001F6FF'  # Transport & Map Symbols
    '\U0001F700-\U0001F77F'  # Alchemical Symbols
    '\U0001F780-\U0001F7FF'  # Geometric Shapes Extended
    '\U0001F800-\U0001F8FF'  # Supplemental Arrows-C
    '\U0001F900-\U0001F9FF'  # Supplemental Symbols & Pictographs
    '\U0001FA00-\U0001FA6F'  # Chess Symbols
    '\U0001FA70-\U0001FAFF'  # Symbols & Pictographs Extended-A
    '\U0001F1E0-\U0001F1FF'  # Flags (iOS/regional indicators)
    '\u2600-\u26FF'          # Misc Symbols (☀, ☁, ☂, etc.)
    '\u2700-\u27BF'          # Dingbats (✂, ✈, ✉, ✌, etc.)
    '\uFE00-\uFE0F'          # Variation Selectors
    '\U000E0100-\U000E01EF'  # Variation Selectors Supplement
    '\U0001F3FB-\U0001F3FF'  # Emoji modifiers (skin tones)
    ']+',
    flags=re.UNICODE
)

# Control characters and zero-width characters to strip
STRIP_CONTROL_RE = re.compile(
    '['
    '\x00-\x08'      # C0 controls (NUL-BS)
    '\x0B\x0C'       # VT, FF
    '\x0E-\x1F'      # C0 controls (SO-US)
    '\x7F-\x9F'      # DEL and C1 controls
    '\u200B-\u200F'  # Zero-width chars, LRM, RLM, etc.
    '\u202A-\u202E'  # Bidi embedding controls
    '\u2060-\u206F'  # Format chars (word joiner, etc.)
    '\uFEFF'         # BOM / Zero Width NBSP
    '\uFFF0-\uFFF8'  # Specials
    ']+',
    flags=re.UNICODE
)

# Surrogates and private use areas
# Shouldn't appear in valid UTF-8, but strip just in case
STRIP_PRIVATE_RE = re.compile(
    '['
    '\uD800-\uDFFF'         # Surrogates
    '\uE000-\uF8FF'         # Private Use Area
    '\uF900-\uFAFF'         # CJK Compatibility Ideographs (keep? strip for safety)
    '\uFE10-\uFE1F'         # Vertical Forms
    '\uFE20-\uFE2F'         # Combining Half Marks
    '\U000F0000-\U000FFFFF' # Supplementary Private Use Area-A
    '\U00100000-\U0010FFFF' # Supplementary Private Use Area-B
    ']+',
    flags=re.UNICODE
)

def strip_modifiers(text):
    def process_characters(text):
        result = []
        i = 0
        while i < len(text):
            char = text[i]
            category = unicodedata.category(char)
            
            if category.startswith(('L', 'N', 'P', 'S')):
                result.append(char)
                i += 1

            elif category.startswith(('M', 'Sk', 'Cf')) or char in '\u200d\u200c':
                i += 1

            else:
                result.append(char)
                i += 1
                
        return ''.join(result)

    if text == None: return None

    for char in invalid_rendering:
        text = text.replace(char, " ")
    
    stripped = process_characters(text)
    stripped = re.sub(r'[\uFE00-\uFE0F]', '', stripped)
    stripped = re.sub(r'[\U000E0100-\U000E01EF]', '', stripped, flags=re.UNICODE)
    stripped = re.sub(r'[\U0001F3FB-\U0001F3FF]', '', stripped, flags=re.UNICODE)
    stripped = re.sub(r'[\u200D\u200C]', '', stripped)
    stripped = re.sub(r'\r\n?', '\n', stripped)
    
    return stripped.strip().replace("\x00", "")

def sanitize_name(name):
    if name is None: return None
    
    # Convert to string and normalize to NFKC
    # NFKC: Compatibility decomposition followed by canonical composition
    # This handles: ① to 1, Ⅰ to I, etc., while keeping composed forms
    name = str(name)
    name = unicodedata.normalize('NFKC', name)
    
    # Build result using category-based filtering
    result = []
    for char in name:
        cat = unicodedata.category(char)
        cat_prefix = cat[0] if cat else 'C'
        
        # Allow letters (L*), numbers (N*), and punctuation (P*)
        if cat_prefix in ('L', 'N', 'P'): result.append(char)
        
        # Allow space separator, normalize to regular space
        elif cat == 'Zs': result.append(' ')

        # Convert line/paragraph separators to space
        elif cat in ('Zl', 'Zp'): result.append(' ')
        
        # Allow spacing combining marks (Mc) for Indic, Hebrew, etc.
        elif cat == 'Mc': result.append(char)
        
        # Allow modifier letters (Lm) - e.g., ʰ, ʱ, ː
        elif cat == 'Lm': result.append(char)
        
        # Strip everything else:
        # - Mn (Nonspacing Mark): diacritics, combining marks (Zalgo)
        # - Me (Enclosing Mark): enclosing combining marks
        # - C* (Controls, Format, Surrogates, Private Use, Unassigned)
        # - S* (Symbols: currency, math, modifiers, other)
    
    name = ''.join(result)
    
    # Additional block-based stripping for symbols that categories missed
    name = STRIP_BLOCKS_RE.sub('', name)
    name = STRIP_CONTROL_RE.sub('', name)
    name = STRIP_PRIVATE_RE.sub('', name)
    
    # Collapse multiple whitespace characters
    name = re.sub(r'\s+', ' ', name)
    
    # Strip leading/trailing whitespace
    name = name.strip()
    
    return name
