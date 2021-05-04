#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""A non-thematic collection of useful functions."""


def recursively_replace(original, replacements, include_original_keys=False):
    """Clones an iterable and recursively replaces specific values."""
    
    # If this function would be called recursively, the parameters 'replacements' and 'include_original_keys' would have to be 
    # passed each time. Therefore, a helper function with a reduced parameter list is used for the recursion, which nevertheless
    # can access the said parameters.
    
    def _recursion_helper(obj):
        #Determine if the object should be replaced. If it is not hashable, the search will throw a TypeError.
        try:
            if obj in replacements:
                return replacements[obj]
        except TypeError:
            pass

        # An iterable is recursively processed depending on its class.
        if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, bytearray)):
            if isinstance(obj, dict):
                contents = {}

                for key, val in obj.items():
                    new_key = _recursion_helper(key) if include_original_keys else key
                    new_val = _recursion_helper(val)

                    contents[new_key] = new_val

            else:
                contents = []

                for element in obj:
                    new_element = _recursion_helper(element)

                    contents.append(new_element)

            # Use the same class as the original.
            return obj.__class__(contents)

        # If it is not replaced and it is not an iterable, return it.
        return obj

    return _recursion_helper(original)
