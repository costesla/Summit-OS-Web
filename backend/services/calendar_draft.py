"use strict";

const START_HOURS = {
    1: 4, 2: 4, 3: 4, 4: 4, 5: 4, 6: 8, 0: 8
};
const END_HOURS = {
    1: 22, 2: 22, 3: 22, 4: 22, 5: 24, 6: 11, 0: 18
};

def get_hours_for_day(date_obj):
    day = date_obj.weekday() # 0=Monday, 6=Sunday
    # Adjust to JS getDay() style if needed (0=Sun, 1=Mon) or map accordingly
    # Python: 0=Mon, 1=Tue... 5=Sat, 6=Sun
    # JS: 0=Sun, 1=Mon...
    
    # Let's map Python weekday to our config keys (using JS style keys for consistency with original code config or just map)
    # Map: Mon(0)->1, Tue(1)->2, Wed(2)->3, Thu(3)->4, Fri(4)->5, Sat(5)->6, Sun(6)->0
    js_day = (day + 1) % 7
    
    start = START_HOURS.get(js_day)
    end = END_HOURS.get(js_day)
    
    if start is None:
        return None
        
    return {"start": start, "end": end}
