from __future__ import division
from math import ceil, floor, isnan
# Derived from asciichartpy |  https://github.com/kroitor/asciichart/blob/master/asciichartpy/__init__.py
class AsciiChart:
    def __init__(self, glyphset="unicode"):
        self.symbols = ['┼', '┤', '╶', '╴', '─', '╰', '╭', '╮', '╯', '│']
        if glyphset == "plain":
            self.symbols = ['+', '|', '-', '-', '-', '\'', ',', '.', '`', '|']
    def plot(self, series, cfg=None):
        if len(series) == 0:
            return ''
        if not isinstance(series[0], list):
            if all(isnan(n) for n in series):
                return ''
            else:
                series = [series]
        cfg = cfg or {}
        minimum = cfg.get('min', min(filter(lambda n: not isnan(n), [j for i in series for j in i])))
        maximum = cfg.get('max', max(filter(lambda n: not isnan(n), [j for i in series for j in i])))
        symbols = cfg.get('symbols', self.symbols)
        if minimum > maximum:
            raise ValueError('The min value cannot exceed the max value.')
        interval = maximum - minimum
        offset = cfg.get('offset', 3)
        height = cfg.get('height', interval)
        ratio = height / interval if interval > 0 else 1

        min2 = int(floor(minimum * ratio))
        max2 = int(ceil(maximum * ratio))

        def clamp(n):
            return min(max(n, minimum), maximum)

        def scaled(y):
            return int(round(clamp(y) * ratio) - min2)

        rows = max2 - min2

        width = 0
        for i in range(0, len(series)):
            width = max(width, len(series[i]))
        width += offset

        placeholder = cfg.get('format', '{:8.2f} ')

        result = [[' '] * width for i in range(rows + 1)]

        for y in range(min2, max2 + 1):
            if callable(placeholder):
                label = placeholder(maximum - ((y - min2) * interval / (rows if rows else 1))).rjust(12)
            else:
                label = placeholder.format(maximum - ((y - min2) * interval / (rows if rows else 1)))

            result[y - min2][max(offset - len(label), 0)] = label
            result[y - min2][offset - 1] = symbols[0] if y == 0 else symbols[1]

        d0 = series[0][0]
        if not isnan(d0):
            result[rows - scaled(d0)][offset - 1] = symbols[0]

        for i in range(0, len(series)):
            for x in range(0, len(series[i]) - 1):
                d0 = series[i][x + 0]
                d1 = series[i][x + 1]

                if isnan(d0) and isnan(d1):
                    continue

                if isnan(d0) and not isnan(d1):
                    result[rows - scaled(d1)][x + offset] = symbols[2]
                    continue

                if not isnan(d0) and isnan(d1):
                    result[rows - scaled(d0)][x + offset] = symbols[3]
                    continue

                y0 = scaled(d0)
                y1 = scaled(d1)
                if y0 == y1:
                    result[rows - y0][x + offset] = symbols[4]
                    continue

                result[rows - y1][x + offset] = symbols[5] if y0 > y1 else symbols[6]
                result[rows - y0][x + offset] = symbols[7] if y0 > y1 else symbols[8]

                start = min(y0, y1) + 1
                end = max(y0, y1)
                for y in range(start, end):
                    result[rows - y][x + offset] = symbols[9]

        return '\n'.join([''.join(row).rstrip() for row in result])