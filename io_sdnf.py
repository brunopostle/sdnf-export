#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# loosely based on io_mesh_stl by Guillaume Bouchard (Guillaum)

bl_info = {
    "name": "SDNF format",
    "author": "Bruno Postle",
    "version": (0, 0, 1),
    "blender": (2, 8, 0),
    "location": "File > Import-Export",
    "description": "Export SDNF files",
    "category": "Import-Export",
}


import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
)
from bpy_extras.io_utils import (
    ExportHelper,
    orientation_helper,
    axis_conversion,
)
from bpy.types import (
    Operator,
    OperatorFileListElement,
)


class ExportSDNF(Operator, ExportHelper):
    bl_idname = "export_mesh.sdnf"
    bl_label = "Export SDNF"
    bl_description = """Save SDNF plate data"""

    filename_ext = ".sdnf"
    filter_glob: StringProperty(default="*.sdnf", options={'HIDDEN'})

    use_selection: BoolProperty(
        name="Selection Only",
        description="Export selected objects only",
        default=False,
    )
    global_scale: FloatProperty(
        name="Scale",
        min=0.01, max=1000.0,
        default=1.0,
    )
    use_scene_unit: BoolProperty(
        name="Scene Unit",
        description="Apply current scene's unit (as defined by unit scale) to exported data",
        default=False,
    )

    def execute(self, context):
        import os
        from mathutils import Matrix

        keywords = self.as_keywords(
            ignore=(
                "use_selection",
                "global_scale",
                "check_existing",
                "filter_glob",
                "use_scene_unit",
            ),
        )

        scene = context.scene
        if self.use_selection:
            data_seq = context.selected_objects
        else:
            data_seq = scene.objects

        # Take into account scene's unit scale, so that 1 inch in Blender gives 1 inch elsewhere! See T42000.
        global_scale = self.global_scale
        if scene.unit_settings.system != 'NONE' and self.use_scene_unit:
            global_scale *= scene.unit_settings.scale_length

        global_matrix = Matrix([[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]) @ Matrix.Scale(global_scale, 4)

        prefix = os.path.splitext(self.filepath)[0]
        keywords_temp = keywords.copy()
        
        surfaces = []
        for ob in data_seq:
            modifiers = ob.modifiers
            thickness = 0.008
            for item in modifiers.items:
                print(item)
                if item.name == "Solidify":
                    thickness = item.thickness
            surfaces.append({"faces": faces_from_mesh(ob, global_matrix), "thickness": thickness})
        keywords_temp["filepath"] = prefix + ".sdnf"
        write_sdnf(surfaces=surfaces, **keywords_temp)

        return {'FINISHED'}

    def draw(self, context):
        pass


class SDNF_PT_export_main(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_MESH_OT_sdnf"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator


class SDNF_PT_export_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_MESH_OT_sdnf"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "use_selection")


class SDNF_PT_export_transform(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Transform"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_MESH_OT_sdnf"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "global_scale")
        layout.prop(operator, "use_scene_unit")


def menu_export(self, context):
    self.layout.operator(ExportSDNF.bl_idname, text="SDNF (.sdnf)")


classes = (
    ExportSDNF,
    SDNF_PT_export_main,
    SDNF_PT_export_include,
    SDNF_PT_export_transform,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_export.append(menu_export)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_export.remove(menu_export)


if __name__ == "__main__":
    register()

def faces_from_mesh(ob, global_matrix):
    """
    From an object, return a generator over a list of faces.

    Each faces is a list of his vertexes. Each vertex is a tuple of
    its coordinate.
    """

    import bpy

    # get the editmode data
    if ob.mode == "EDIT":
        ob.update_from_editmode()

    mesh_owner = ob

    # Object.to_mesh() is not guaranteed to return a mesh.
    try:
        mesh = mesh_owner.to_mesh()
    except RuntimeError:
        return

    if mesh is None:
        return

    mat = global_matrix @ ob.matrix_world
    mesh.transform(mat)
    if mat.is_negative:
        mesh.flip_normals()

    vertices = mesh.vertices

    for polygon in mesh.polygons:
        yield [vertices[index].co.copy() for index in polygon.vertices]

    mesh_owner.to_mesh_clear()


def write_sdnf(filepath, surfaces):

    with open(filepath, 'w') as data:
        fw = data.write

        total_faces = 0
        surfaces_iterated = []
        for surface in surfaces:
            surface_iterated = []
            for face in surface["faces"]:
                total_faces += 1
                surface_iterated.append({"face": face, "thickness": surface["thickness"]})
            surfaces_iterated.append(surface_iterated)

        # 00 Title Packet

        fw('Packet 00\n')
        fw('""\n')
        fw('"Eng Firm Id"\n')
        fw('"Client Id"\n')
        fw('"Structure Id"\n')
        fw('"10/02/13" "16:27:18"\n')
        fw('1 "_Issue_Code_"\n')
        fw('"_Design_Code_"\n')
        fw('0\n')

        # 20 Plate elements

        fw('Packet 20\n')

        # linear units, thickness units, and number of elements

        fw('"meters" "meters" ' + str(total_faces) + "\n")

        face_index = 200001
        thickness = 0.008

        for surface in surfaces_iterated:

            for item in surface:
                face = item["face"]
                thickness = item["thickness"]

                # Member ID; Cardinal Point; Class?
                fw(str(face_index) + " 1 0 0 \"plate\"\n")

                # Piece mark; Grade, Thickness, number of nodes
                fw('"" "S355" ' + str(thickness) + ' ' + str(len(face)) + "\n")

                for vert in face:
                    fw('%f %f %f\n' % vert[:])
                face_index += 1
