"""Engine policy on shared contextual evidence."""
from .qualification import evaluate as qualify

def evaluate(identity,page,geo):
    return qualify('STARTUPS',identity,page,geo)
