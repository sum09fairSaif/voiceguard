"""The sentences users read aloud, for the voice check and for enrollment.

Each one is built from a fixed pattern with every slot filled at random:

    The sleepy tiger polished the rusty lantern near the bridge.

so it reads like a real sentence but can't be predicted, which is what stops
someone replaying an old recording of the user. With the lists below there
are about 5 billion different sentences.

Only the six key words (the creature and what it's like, the action, the
thing and what it's like, and the place) are checked. "the" and the words
for where (near, under, ...) are left out of the check (UNCHECKED_WORDS):
speech-to-text drops or swaps small words easily, and a real user shouldn't
fail for that.

Every word is common, concrete and easy to read aloud, and speech-to-text
spells it back the same way: no number words or words that sound like one
(won, ate), no words that sound like another word (sea/see, hid/hit), and no
British/American spelling pairs (harbor/harbour).
"""

import secrets

# Who does the action, and what they're like.
CREATURES = [
    "baker", "beaver", "camel", "chicken", "dolphin", "donkey", "dragon",
    "eagle", "falcon", "farmer", "giraffe", "goose", "hamster", "kitten",
    "koala", "lizard", "lobster", "monkey", "otter", "panda", "parrot",
    "penguin", "pilot", "puppy", "rabbit", "robot", "sailor", "sparrow",
    "squirrel", "tiger", "turtle", "wizard", "zebra",
]
CREATURE_WORDS = [
    "brave", "cheerful", "clever", "curious", "friendly", "gentle", "giant",
    "grumpy", "happy", "humble", "hungry", "jolly", "lonely", "lucky",
    "noisy", "patient", "polite", "proud", "sleepy", "tiny",
]
ACTIONS = [
    "admired", "balanced", "borrowed", "buried", "carried", "chased",
    "cleaned", "collected", "delivered", "dragged", "dropped", "fixed",
    "followed", "found", "guarded", "hugged", "juggled", "lifted", "noticed",
    "packed", "painted", "polished", "pulled", "pushed", "rescued", "tossed",
    "washed", "wrapped",
]
# What the action is done to, and what it's like.
THINGS = [
    "anchor", "apple", "basket", "bottle", "button", "camera", "candle",
    "carpet", "cherry", "compass", "cookie", "crystal", "feather", "glove",
    "guitar", "hammer", "helmet", "jacket", "journal", "kettle", "ladder",
    "lantern", "laptop", "lemon", "magnet", "marble", "mirror", "muffin",
    "napkin", "needle", "notebook", "orange", "paddle", "pebble", "pencil",
    "pepper", "pillow", "pumpkin", "puzzle", "quilt", "ribbon", "rocket",
    "saddle", "spoon", "sweater", "teapot", "ticket", "tomato", "trumpet",
    "umbrella", "violin", "wagon", "wallet", "walnut", "whistle",
]
THING_WORDS = [
    "ancient", "bright", "broken", "crooked", "dusty", "fancy", "frozen",
    "fuzzy", "golden", "heavy", "muddy", "purple", "rusty", "shiny",
    "spotted", "sticky", "striped", "tidy", "velvet", "wooden",
]
# Where it happens.
PLACES = [
    "barn", "bridge", "castle", "cottage", "desert", "forest", "fountain",
    "garden", "island", "jungle", "kitchen", "library", "lighthouse",
    "market", "meadow", "mountain", "ocean", "orchard", "playground", "river",
    "stadium", "station", "tunnel", "valley", "village",
]
NEAR_WORDS = ["above", "across", "around", "behind", "below", "beside", "beyond", "inside", "near", "under"]

# Read aloud but not checked: speech-to-text drops or swaps them easily.
UNCHECKED_WORDS = frozenset({"the", "a", "an", *NEAR_WORDS})

# How many words in each passage are checked.
KEY_WORDS_PER_PASSAGE = 6

# The operating system's secure randomness, so passages can't be predicted.
_random = secrets.SystemRandom()


def generate_passage() -> str:
    """A fresh sentence, e.g. "The sleepy tiger polished the rusty lantern near the bridge." """
    pick = _random.choice
    return (
        f"The {pick(CREATURE_WORDS)} {pick(CREATURES)} {pick(ACTIONS)} the {pick(THING_WORDS)} {pick(THINGS)} "
        f"{pick(NEAR_WORDS)} the {pick(PLACES)}."
    )
