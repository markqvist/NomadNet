import re
import unicodedata

invalid_rendering = ["🕵️", "☝"]

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

    for char in invalid_rendering:
        text = text.replace(char, " ")
    
    stripped = process_characters(text)
    stripped = re.sub(r'[\uFE00-\uFE0F]', '', stripped)
    stripped = re.sub(r'[\U000E0100-\U000E01EF]', '', stripped, flags=re.UNICODE)
    stripped = re.sub(r'[\U0001F3FB-\U0001F3FF]', '', stripped, flags=re.UNICODE)
    stripped = re.sub(r'[\u200D\u200C]', '', stripped)
    stripped = re.sub(r'\r\n?', '\n', stripped)
    
    return stripped
