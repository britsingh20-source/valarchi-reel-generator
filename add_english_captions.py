"""
Adds English caption_en to every scene in topics.json.
Run once: python add_english_captions.py
"""
import json
from pathlib import Path

# Full English scene captions for topics 1-10
ENGLISH_SCENES = {
    1: [  # rubber
        "Did You Know?", "The Rubber Tree", "When Tapped with a Knife",
        "White Liquid Flows", "Called Latex", "It's Latex!",
        "Collected & Processed", "Used to Make Tires", "Erasers Too!",
        "Amazing Nature!"
    ],
    2: [  # honey
        "Did You Know?", "For 1 Kg of Honey", "A Single Bee",
        "Visits Millions of Flowers", "Its Entire Lifetime",
        "Collects Nectar", "Stores in Hive", "Water Evaporates",
        "Honey is Formed", "Nature's Wonder!"
    ],
    3: [  # salt
        "Did You Know?", "The Salt We Eat", "Comes from the Ocean",
        "Seawater is Collected", "Sun Evaporates the Water",
        "Only Salt Remains", "Gujarat, India", "Produces 1/3 of World's Salt",
        "Hard Work of Farmers", "Amazing Fact!"
    ],
    4: [  # silk
        "Did You Know?", "Silk Comes from", "A Tiny Worm",
        "Silkworm Spins a Cocoon", "One Thread — 1.5 Km Long",
        "Boiled to Get Silk", "Soft & Strong", "Used for Centuries",
        "India Leads Production", "Nature's Finest Fabric!"
    ],
    5: [  # coconut
        "Did You Know?", "The Coconut Tree", "Called Tree of Life",
        "Every Part is Useful", "Water Inside is Sterile", "Used as IV Fluid in War",
        "Shell Becomes Charcoal", "Leaves Make Roofs", "Coconut Oil Uses",
        "Amazing Palm Tree!"
    ],
    6: [  # rice
        "Did You Know?", "Rice Feeds", "Half the World's Population",
        "Takes 3000 Litres of Water", "To Grow 1 Kg of Rice",
        "Over 40,000 Varieties", "Exist Worldwide", "Rice Paddies Produce",
        "Methane Gas Too", "World's Most Eaten Food!"
    ],
    7: [  # glass
        "Did You Know?", "Glass is Made from", "Plain Sand!",
        "Sand is Melted at 1700°C", "Pure Liquid Glass Forms",
        "Shaped While Hot", "Cools into Glass", "Glass is 100% Recyclable",
        "Lightning Melts Sand Too", "Making Natural Glass!"
    ],
    8: [  # coffee
        "Did You Know?", "Coffee is the", "World's 2nd Traded Commodity",
        "After Oil!", "Coffee Beans are Seeds",
        "Of a Red Fruit", "It Takes 3-4 Years", "For a Tree to Fruit",
        "Wakes Up the World", "Every Single Day!"
    ],
    9: [  # ocean
        "Did You Know?", "71% of Earth", "Is Ocean!",
        "But We've Explored", "Only 5% of It",
        "Mariana Trench", "Is 11 Km Deep", "Mt. Everest Would Sink!",
        "Unknown Life Forms", "Still Undiscovered!"
    ],
    10: [  # sleep
        "Did You Know?", "During Sleep", "Your Brain Organizes Info",
        "Kids Need", "10-12 Hours of Sleep", "Adults Need",
        "7-8 Hours", "Lack of Sleep", "Weakens Immunity",
        "Sleep Well Tonight!"
    ],
}

# Generic English scene template for topics 11-97
GENERIC_SCENE_LABELS = [
    "Did You Know?", "Fact #1", "Fact #2", "Fact #3", "Fact #4",
    "Fact #5", "Fact #6", "Fact #7", "Fact #8", "Amazing Fact!"
]

# Specific overrides for topics 11-97 based on topic name
TOPIC_SCENE_OVERRIDES = {
    "spider_web":    ["Did You Know?","Spider Silk","Stronger Than Steel","5x Tougher","Than Kevlar","Stretches Without Breaking","One Strand","Can Span Metres","Nature's Engineering","Mind Blowing!"],
    "banana":        ["Did You Know?","Bananas are","Slightly Radioactive","They Contain K-40","A Natural Isotope","But It's Safe!","Bananas Float","In Water","Curved Shape Helps","Nature's Snack!"],
    "lightning":     ["Did You Know?","Lightning Strikes","Earth 100 Times","Every Second!","Temperature is","30,000 Kelvin","5x Hotter Than the Sun","Lasts Only","0.2 Seconds","Incredible Power!"],
    "fingerprint":   ["Did You Know?","No Two Fingerprints","Are Identical","Not Even Twins!","Fingerprints Form","In the Womb","By Week 10","Used for ID","For 100+ Years","Unique to You!"],
    "heart":         ["Did You Know?","Your Heart Beats","100,000 Times a Day","Every Single Day","That's 2.5 Billion","Beats in a Lifetime","Heart Pumps","5 Litres of Blood","Every Minute","Amazing Organ!"],
    "brain":         ["Did You Know?","The Human Brain","Uses 20% of Body's Energy","Has 86 Billion Neurons","Each Connected","To 10,000 Others","Brain Generates","12-25 Watts of Power","Enough to Light a Bulb","Most Complex Organ!"],
    "water":         ["Did You Know?","Water Exists","In 3 States","Solid, Liquid, Gas","Water Has Memory","It Expands When Frozen","Most Life on Earth","Needs Water","97% is Salty Ocean","Protect Freshwater!"],
    "sun":           ["Did You Know?","The Sun","Is 4.6 Billion Years Old","Light Takes 8 Minutes","To Reach Earth","The Sun Loses","4 Million Tonnes","Of Mass Per Second","It Will Shine","For 5 Billion More Years!"],
    "moon":          ["Did You Know?","The Moon","Is Moving Away","From Earth","By 3.8 cm Per Year","Moon Controls Tides","It Slows Earth's Rotation","Once Moon Was","Much Closer","Incredible Cosmic Dance!"],
    "diamond":       ["Did You Know?","Diamonds Are","Pure Carbon","Formed Deep Underground","Under Extreme Pressure","Takes Billions of Years","Hardest Natural Material","On Earth","Diamonds Are Forever","Literally!"],
}

def get_english_scenes(topic_id, topic_name, scene_count):
    if topic_id in ENGLISH_SCENES:
        base = ENGLISH_SCENES[topic_id]
    elif topic_name in TOPIC_SCENE_OVERRIDES:
        base = TOPIC_SCENE_OVERRIDES[topic_name]
    else:
        base = GENERIC_SCENE_LABELS
    # Pad or trim to match scene count
    result = []
    for i in range(scene_count):
        if i < len(base):
            result.append(base[i])
        else:
            result.append(f"Fact #{i}")
    return result

# Load topics
topics_file = Path("topics.json")
with open(topics_file, encoding="utf-8") as f:
    topics = json.load(f)

# Add caption_en to every scene
for topic in topics:
    tid = topic["id"]
    tname = topic["topic"].replace(" ", "_").lower()
    scenes = topic.get("scenes", [])
    en_captions = get_english_scenes(tid, tname, len(scenes))
    for i, scene in enumerate(scenes):
        scene["caption_en"] = en_captions[i]

# Save back
with open(topics_file, "w", encoding="utf-8") as f:
    json.dump(topics, f, ensure_ascii=False, indent=2)

print(f"Updated {len(topics)} topics with English captions")
# Verify
t = topics[0]
print(f"Topic 1 scene 0: {t['scenes'][0]['caption']} -> {t['scenes'][0]['caption_en']}")
print(f"Topic 1 scene 3: {t['scenes'][3]['caption']} -> {t['scenes'][3]['caption_en']}")
