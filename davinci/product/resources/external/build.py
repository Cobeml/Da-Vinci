import cadquery as cq


def build(parameters, interfaces):
    model = cq.Workplane('XY').box(40, 20, parameters['thickness'])
    return cq.Assembly(model)
