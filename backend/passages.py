import secrets

# Common, concrete English words that are easy to read aloud and easy for
# speech-to-text to spell back the same way. No number words, no words that
# sound like another word (sea/see), and no British/American spelling pairs.
WORDS = [
    "anchor", "apple", "basket", "bottle", "bridge", "butter", "button",
    "cactus", "camera", "candle", "carpet", "castle", "cherry", "circle",
    "compass", "cookie", "crystal", "desert", "doctor", "dolphin", "dragon",
    "eagle", "engine", "falcon", "feather", "finger", "forest", "garden",
    "garlic", "glove", "gravel", "guitar", "hammer", "helmet", "honey",
    "igloo", "insect", "island", "jacket", "journal", "jungle", "kettle",
    "kingdom", "kitten", "ladder", "lantern", "laptop", "lemon", "lizard",
    "lobster", "magnet", "marble", "meadow", "mirror", "monkey", "mountain",
    "muffin", "napkin", "needle", "notebook", "ocean", "orange", "orchard",
    "oyster", "paddle", "panda", "parrot", "pebble", "pencil", "pepper",
    "picnic", "pillow", "planet", "pocket", "pumpkin", "puzzle", "quilt",
    "rabbit", "rainbow", "ribbon", "river", "robot", "rocket", "saddle",
    "shadow", "silver", "sparrow", "spider", "spoon", "statue", "sugar",
    "summer", "sweater", "teapot", "thunder", "ticket", "tiger", "tomato",
    "tractor", "trumpet", "tulip", "tunnel", "turtle", "umbrella", "valley",
    "velvet", "village", "violin", "wagon", "wallet", "walnut", "whistle",
    "window", "winter", "wizard", "yellow", "zebra",
]

WORDS_PER_PASSAGE = 6

# The operating system's secure randomness, so passages can't be predicted.
_random = secrets.SystemRandom()


def generate_passage() -> str:
    return " ".join(_random.sample(WORDS, WORDS_PER_PASSAGE))
