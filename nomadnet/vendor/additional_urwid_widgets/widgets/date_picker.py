#! /usr/bin/env python3
# -*- coding: utf-8 -*-


from ..assisting_modules.modifier_key import MODIFIER_KEY        # pylint: disable=unused-import
from ..assisting_modules.useful_functions import recursively_replace
from .indicative_listbox import IndicativeListBox
from .integer_picker import IntegerPicker
from .selectable_row import SelectableRow

import calendar
import datetime
import enum
import urwid


class DatePicker(urwid.WidgetWrap):
    """Serves as a selector for dates."""
    
    _TYPE_ERR_MSG = "type {} was expected for {}, but found: {}."
    _VALUE_ERR_MSG = "unrecognized value: {}."

    # These values are interpreted during the creation of the list items for the day picker.
    class DAY_FORMAT(enum.Enum):
        DAY_OF_MONTH = 1
        DAY_OF_MONTH_TWO_DIGIT = 2
        WEEKDAY = 3
        
    # These values are interpreted during the initialization and define the arrangement of the pickers.
    class PICKER(enum.Enum):
        YEAR = 1
        MONTH = 2
        DAY = 3
    
    # Specifies which dates are selectable.
    class RANGE(enum.Enum):
        ALL = 1
        ONLY_PAST = 2
        ONLY_FUTURE = 3
    
    def __init__(self, initial_date=datetime.date.today(), *, date_range=RANGE.ALL, month_names=calendar.month_name, day_names=calendar.day_abbr,
                 day_format=(DAY_FORMAT.WEEKDAY, DAY_FORMAT.DAY_OF_MONTH), columns=(PICKER.DAY, PICKER.MONTH, PICKER.YEAR),
                 modifier_key=MODIFIER_KEY.CTRL, return_unused_navigation_input=False, year_jump_len=50, space_between=2, 
                 min_width_each_picker=9, year_align="center", month_align="center", day_align="center", topBar_align="center", 
                 topBar_endCovered_prop=("▲", None, None), topBar_endExposed_prop=("───", None, None), bottomBar_align="center",
                 bottomBar_endCovered_prop=("▼", None, None), bottomBar_endExposed_prop=("───", None, None), highlight_prop=(None, None)):
        assert (type(date_range) == self.__class__.RANGE), self.__class__._TYPE_ERR_MSG.format("<enum 'DatePicker.RANGE'>",
                                                                                               "'date_range'",
                                                                                               type(date_range))
        
        for df in day_format:
            assert (type(df) == self.__class__.DAY_FORMAT), self.__class__._TYPE_ERR_MSG.format("<enum 'DatePicker.DAY_FORMAT'>",
                                                                                                "all elements of 'day_format'",
                                                                                                type(df))
        
        # Relevant for 'RANGE.ONLY_PAST' and 'RANGE.ONLY_FUTURE' to limit the respective choices.
        self._initial_year = initial_date.year
        self._initial_month = initial_date.month
        self._initial_day = initial_date.day
        
        # The date pool can be limited, so that only past or future dates are selectable. The initial date is included in the
        # pool.
        self._date_range = date_range
        
        # The presentation of months and weekdays can be changed by passing alternative values (e.g. abbreviations or numerical
        # representations).
        self._month_names = month_names
        self._day_names = day_names
        
        # Since there are different needs regarding the appearance of the day picker, an iterable can be passed, which allows a
        # customization of the presentation.
        self._day_format = day_format
        
        # Specifies the text alignment of the individual pickers. The year alignment is passed directly to the year picker.
        self._month_align = month_align
        self._day_align = day_align
        
        # The default style of a list entry. Since only one list entry will be visible at a time and there is also off focus 
        # highlighting, the normal value can be 'None' (it is never shown).
        self._item_attr = (None, highlight_prop[0])
        
        # A full list of months. (From 'January' to 'December'.)
        self._month_list = self._generate_months()
        
        # Set the respective values depending on the date range.
        min_year = datetime.MINYEAR
        max_year = datetime.MAXYEAR
        
        month_position = self._initial_month - 1
        day_position = self._initial_day - 1
        
        if date_range == self.__class__.RANGE.ALL:
            initial_month_list = self._month_list
            
        elif date_range == self.__class__.RANGE.ONLY_PAST:
            max_year = self._initial_year
            
            # The months of the very last year may be shorten.
            self._shortened_month_list = self._generate_months(end=self._initial_month)
            initial_month_list = self._shortened_month_list
            
        elif date_range == self.__class__.RANGE.ONLY_FUTURE:
            min_year = self._initial_year
            
            # The months of the very first year may be shorten.
            self._shortened_month_list = self._generate_months(start=self._initial_month)
            initial_month_list = self._shortened_month_list
            
            # The list may not start at 1 but some other day of month, therefore use the first list item.
            month_position = 0
            day_position = 0
            
        else:
            raise ValueError(self.__class__._VALUE_ERR_MSG.format(date_range))
        
        # Create pickers.
        self._year_picker = IntegerPicker(self._initial_year,
                                          min_v=min_year,
                                          max_v=max_year,
                                          jump_len=year_jump_len,
                                          on_selection_change=self._year_has_changed,
                                          modifier_key=modifier_key,
                                          return_unused_navigation_input=return_unused_navigation_input,
                                          topBar_align=topBar_align,
                                          topBar_endCovered_prop=topBar_endCovered_prop,
                                          topBar_endExposed_prop=topBar_endExposed_prop,
                                          bottomBar_align=bottomBar_align,
                                          bottomBar_endCovered_prop=bottomBar_endCovered_prop,
                                          bottomBar_endExposed_prop=bottomBar_endExposed_prop,
                                          display_syntax="{:04}",
                                          display_align=year_align,
                                          display_prop=highlight_prop)
        
        self._month_picker = IndicativeListBox(initial_month_list,
                                               position=month_position,
                                               on_selection_change=self._month_has_changed,
                                               modifier_key=modifier_key,
                                               return_unused_navigation_input=return_unused_navigation_input,
                                               topBar_align=topBar_align,
                                               topBar_endCovered_prop=topBar_endCovered_prop,
                                               topBar_endExposed_prop=topBar_endExposed_prop,
                                               bottomBar_align=bottomBar_align,
                                               bottomBar_endCovered_prop=bottomBar_endCovered_prop,
                                               bottomBar_endExposed_prop=bottomBar_endExposed_prop,
                                               highlight_offFocus=highlight_prop[1])
        
        self._day_picker = IndicativeListBox(self._generate_days(self._initial_year, self._initial_month),
                                             position=day_position,
                                             modifier_key=modifier_key,
                                             return_unused_navigation_input=return_unused_navigation_input,
                                             topBar_align=topBar_align,
                                             topBar_endCovered_prop=topBar_endCovered_prop,
                                             topBar_endExposed_prop=topBar_endExposed_prop,
                                             bottomBar_align=bottomBar_align,
                                             bottomBar_endCovered_prop=bottomBar_endCovered_prop,
                                             bottomBar_endExposed_prop=bottomBar_endExposed_prop,
                                             highlight_offFocus=highlight_prop[1])
        
        # To mimic a selection widget, 'IndicativeListbox' is wrapped in a 'urwid.BoxAdapter'. Since two rows are used for the bars,
        # size 3 makes exactly one list item visible.
        boxed_month_picker = urwid.BoxAdapter(self._month_picker, 3)
        boxed_day_picker = urwid.BoxAdapter(self._day_picker, 3)
        
        # Replace the 'DatePicker.PICKER' elements of the parameter 'columns' with the corresponding pickers.
        replacements = {self.__class__.PICKER.YEAR  : self._year_picker,
                        self.__class__.PICKER.MONTH : boxed_month_picker,
                        self.__class__.PICKER.DAY   : boxed_day_picker}
        
        columns = recursively_replace(columns, replacements)
        
        # wrap 'urwid.Columns'
        super().__init__(urwid.Columns(columns,
                                       min_width=min_width_each_picker,
                                       dividechars=space_between))
    
    def __repr__(self):
        return "{}(date='{}', date_range='{}', initial_date='{}-{:02}-{:02}', selected_date='{}')".format(self.__class__.__name__,
                                                                                                          self.get_date(),
                                                                                                          self._date_range,
                                                                                                          self._initial_year,
                                                                                                          self._initial_month,
                                                                                                          self._initial_day,
                                                                                                          self.get_date())
    
    # The returned widget is used for all list entries.
    def _generate_item(self, cols, *, align="center"):
        return urwid.AttrMap(SelectableRow(cols, align=align),
                             self._item_attr[0],
                             self._item_attr[1])
    
    def _generate_months(self, start=1, end=12):
        months = []
        
        for month in range(start, end+1):
            item = self._generate_item([self._month_names[month]], align=self._month_align)
            
            # Add a new instance variable which holds the numerical value. This makes it easier to get the displayed value.
            item._numerical_value = month
            
            months.append(item)
        
        return months
    
    def _generate_days(self, year, month):
        start = 1
        weekday, end = calendar.monthrange(year, month)         # end is included in the range
        
        # If the date range is 'ONLY_PAST', the last month does not end as usual but on the specified day.
        if (self._date_range == self.__class__.RANGE.ONLY_PAST) and (year == self._initial_year) and (month == self._initial_month):
            end = self._initial_day
        
        # If the date range is 'ONLY_FUTURE', the first month does not start as usual but on the specified day.
        elif (self._date_range == self.__class__.RANGE.ONLY_FUTURE) and (year == self._initial_year) and (month == self._initial_month):
            start = self._initial_day
            weekday = calendar.weekday(year, month, start)
        
        days = []
        
        for day in range(start, end+1):
            cols = []
            
            # The 'DatePicker.DAY_FORMAT' elements of the iterable are translated into columns of the day picker. This allows the
            # presentation to be customized.
            for df in self._day_format:
                if df == self.__class__.DAY_FORMAT.DAY_OF_MONTH:
                    cols.append(str(day))
                    
                elif df == self.__class__.DAY_FORMAT.DAY_OF_MONTH_TWO_DIGIT:
                    cols.append(str(day).zfill(2))
                    
                elif df == self.__class__.DAY_FORMAT.WEEKDAY:
                    cols.append(self._day_names[weekday])
                    
                else:
                    raise ValueError(self.__class__._VALUE_ERR_MSG.format(df))
            
            item = self._generate_item(cols, align=self._day_align)
            
            # Add a new instance variable which holds the numerical value. This makes it easier to get the displayed value.
            item._numerical_value = day
            
            # Keeps track of the weekday.
            weekday = (weekday + 1) if (weekday < 6) else 0
            
            days.append(item)
        
        return days
    
    def _year_has_changed(self, previous_year, current_year):
        month_position_before_change = self._month_picker.get_selected_position()
        
        # Since there are no years in 'RANGE.ALL' that do not have the full month range, the body never needs to be changed after
        # initialization.
        if self._date_range != self.__class__.RANGE.ALL:
            # 'None' stands for trying to keep the old value.
            provisional_position = None
            
            # If the previous year was the specified year, the shortened month range must be replaced by the complete one. If this
            # shortened month range does not begin at 'January', then the difference must be taken into account.
            if previous_year == self._initial_year:
                if self._date_range == self.__class__.RANGE.ONLY_FUTURE:
                    provisional_position = self._month_picker.get_selected_item()._numerical_value - 1
                    
                self._month_picker.set_body(self._month_list,
                                            alternative_position=provisional_position)
            
            # If the specified year is selected, the full month range must be replaced with the shortened one.
            elif current_year == self._initial_year:
                if self._date_range == self.__class__.RANGE.ONLY_FUTURE:
                    provisional_position = month_position_before_change - (self._initial_month - 1)
                    
                self._month_picker.set_body(self._shortened_month_list,
                                            alternative_position=provisional_position)
    
        # Since the month has changed, the corresponding method is called.
        self._month_has_changed(month_position_before_change,
                                self._month_picker.get_selected_position(),
                                previous_year=previous_year)
    
    def _month_has_changed(self, previous_position, current_position, *, previous_year=None):
        # 'None' stands for trying to keep the old value.
        provisional_position = None
        
        current_year = self._year_picker.get_value()
        
        # Out of range values are changed by 'IndicativeListBox' to the nearest valid values.
        
        # If the date range is 'ONLY_FUTURE', it may be that a month does not start on the first day. In this case, the value must
        # be changed to reflect this difference.
        if self._date_range == self.__class__.RANGE.ONLY_FUTURE:
            # If the current or previous year is the specified year and the month was the specified month, the value has an offset
            # of the specified day. Therefore the deposited numerical value is used. ('-1' because it's an index.)
            if ((current_year == self._initial_year) or (previous_year == self._initial_year)) and (previous_position == 0):
                provisional_position = self._day_picker.get_selected_item()._numerical_value - 1
            
            # If the current year is the specified year and the current month is the specified month, the month begins not with 
            # the first day, but with the specified day.
            elif (current_year == self._initial_year) and (current_position == 0):
                provisional_position = self._day_picker.get_selected_position() - (self._initial_day - 1)
            
        self._day_picker.set_body(self._generate_days(current_year,
                                                      self._month_picker.get_selected_item()._numerical_value),
                                  alternative_position=provisional_position)
        
    def get_date(self):
        return datetime.date(self._year_picker.get_value(),
                             self._month_picker.get_selected_item()._numerical_value,
                             self._day_picker.get_selected_item()._numerical_value)
        
    def set_date(self, date):
        # If the date range is limited, test for the new limit.
        if self._date_range != self.__class__.RANGE.ALL:
            limit = datetime.date(self._initial_year, self._initial_month, self._initial_day)
            
            if (self._date_range == self.__class__.RANGE.ONLY_PAST) and (date > limit):
                raise ValueError("The passed date is outside the upper bound of the date range.")
            
            elif (self._date_range == self.__class__.RANGE.ONLY_FUTURE) and (date < limit):
                raise ValueError("The passed date is outside the lower bound of the date range.")
            
        year = date.year
        month = date.month
        day = date.day
        
        # Set the new values, if needed.
        if year != self._year_picker.get_value():
            self._year_picker.set_value(year)
        
        if month != self._month_picker.get_selected_item()._numerical_value:
            month_position = month - 1          # '-1' because it's an index.
            
            if (self._date_range == self.__class__.RANGE.ONLY_FUTURE) and (year == self._initial_year):
                # If the value should be negative, the behavior of 'IndicativeListBox' shows effect and position 0 is selected.
                month_position = month_position - (self._initial_month - 1)
            
            self._month_picker.select_item(month_position)
        
        if day != self._day_picker.get_selected_item()._numerical_value:
            day_position = day - 1              # '-1' because it's an index.
            
            if (self._date_range == self.__class__.RANGE.ONLY_FUTURE) and (year == self._initial_year) and (month == self._initial_month):
                day_position = day_position - (self._initial_day - 1)
            
            self._day_picker.select_item(day_position)
    