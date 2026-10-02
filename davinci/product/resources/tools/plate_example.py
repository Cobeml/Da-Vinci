"""Example proposal, not implicitly trusted or registered. Tests live separately."""

SOURCE = """import cadquery as cq

def run(arguments):
    plate = cq.Workplane('XY').box(arguments['length'], arguments['width'], arguments['thickness'], centered=(True, True, False))
    holes = cq.Workplane('XY').pushPoints(arguments['holes']).circle(arguments['radius']).extrude(arguments['thickness'])
    return plate.cut(holes).translate(arguments['translation'])
"""

# Real regression: symmetric origin-only fixtures miss a lost placement transform.
BROKEN = SOURCE.replace(".translate(arguments['translation'])", "")
# Preserves volume and bounds while moving holes: volume alone cannot detect this.
MISLEADING = SOURCE.replace("arguments['holes']", "[(-x, -y) for x, y in arguments['holes']]")
