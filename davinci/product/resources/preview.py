"""Trusted preview from exported STEP, never candidate-produced glTF or code."""
import cadquery as cq

shape = cq.importers.importStep('/input/model.step')
assembly = cq.Assembly(name='evaluated_geometry')
assembly.add(shape, name='part', color=cq.Color(0.83, 0.49, 0.27))
assembly.export('/output/model.glb')
