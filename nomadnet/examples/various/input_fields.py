#!/usr/bin/env python3
import os
env_string = ""
for e in os.environ:
  env_string += "{}={}\n".format(e, os.environ[e])

template = """>Fields and Submitting Data

Nomad Network let's you use simple input fields for submitting data to node-side applications. Submitted data, along with other session variables will be available to the node-side script / program as environment variables. This page contains a few examples.

>> Read Environment Variables

{@ENV}
>>Examples of Fields and Submissions

The following section contains a simple set of fields, and a few different links that submit the field data in different ways.

-=


>>>Text Fields
An input field    : `B444`<username`Entered data>`b

An masked field   : `B444`<!|password`Value of Field>`b

An small field    : `B444`<8|small`test>`b, and some more text.

Two fields        : `B444`<8|one`One>`b `B444`<8|two`Two>`b

The data can be `!`[submitted`:/page/input_fields.mu`username|two]`!.

>> Checkbox Fields

`B444`<?|sign_up|1|*`>`b Sign me up 

>> Radio group

Select your favorite color:

`B900`<^|color|Red`>`b  Red

`B090`<^|color|Green`>`b Green

`B009`<^|color|Blue`>`b Blue


>>> Submitting data

You can `!`[submit`:/page/input_fields.mu`one|password|small|color]`! other fields, or just `!`[a single one`:/page/input_fields.mu`username]`!

Or simply `!`[submit them all`:/page/input_fields.mu`*]`!.

Submission links can also `!`[include pre-configured variables`:/page/input_fields.mu`username|two|entitiy_id=4611|action=view]`!.

Or take all fields and `!`[pre-configured variables`:/page/input_fields.mu`*|entitiy_id=4611|action=view]`!.

Or only `!`[pre-configured variables`:/page/input_fields.mu`entitiy_id=4688|task=something]`!

-=

"""
print(template.replace("{@ENV}", env_string))