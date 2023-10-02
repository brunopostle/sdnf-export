import bpy

from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
)
from bpy_extras.io_utils import (
    ExportHelper,
)
from bpy.types import (
    Operator,
)

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
# 2023 Bruno Postle <bruno@postle.net>
# loosely based on io_mesh_stl by Guillaume Bouchard (Guillaum)

bl_info = {
    "name": "SDNF format",
    "author": "Bruno Postle",
    "version": (0, 0, 1),
    "blender": (2, 80, 0),
    "location": "File > Import-Export",
    "description": "Export SDNF files",
    "category": "Import-Export",
}


class ExportSDNF(Operator, ExportHelper):
    bl_idname = "export_mesh.sdnf"
    bl_label = "Export SDNF"
    bl_description = """Save SDNF plate data"""

    filename_ext = ".sdnf"
    filter_glob: StringProperty(default="*.sdnf", options={"HIDDEN"})

    use_selection: BoolProperty(
        name="Selection Only",
        description="Export selected objects only",
        default=False,
    )
    global_scale: FloatProperty(
        name="Scale",
        min=0.01,
        max=1000.0,
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

        # Take into account scene's unit scale, so that 1 inch in Blender
        # gives 1 inch elsewhere! See T42000.
        global_scale = self.global_scale
        if scene.unit_settings.system != "NONE" and self.use_scene_unit:
            global_scale *= scene.unit_settings.scale_length

        prefix = os.path.splitext(self.filepath)[0]
        keywords_temp = keywords.copy()

        polygons = []
        edges = []
        for ob in data_seq:

            thickness = 0.008
            offset = 0.000
            for item in ob.modifiers:
                if item.name == "Solidify":
                    thickness = item.thickness
                    offset = item.offset

            dat = faces_from_mesh(ob, Matrix.Scale(global_scale, 4))

            for polygon in dat["polygons"]:
                polygons.append(
                    {
                        "polygon": polygon,
                        "thickness": thickness,
                        "offset": offset,
                        "name": ob.name,
                    }
                )
            for edge in dat["edges"]:
                edges.append(
                    {
                        "edge": edge,
                        "section": "UC152x152x23",
                        "name": ob.name,
                    }
                )

        keywords_temp["filepath"] = prefix + ".sdnf"
        write_sdnf(polygons=polygons, edges=edges, **keywords_temp)

        return {"FINISHED"}

    def draw(self, context):
        pass


class SDNF_PT_export_main(bpy.types.Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = ""
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"HIDE_HEADER"}

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
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
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
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
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

    # get the editmode data
    if ob.mode == "EDIT":
        ob.update_from_editmode()

    mesh_owner = ob

    # Object.to_mesh() is not guaranteed to return a mesh.
    try:
        mesh = mesh_owner.to_mesh()
    except RuntimeError:
        return {"polygons": [], "edges": []}

    if mesh is None:
        return {"polygons": [], "edges": []}

    mat = global_matrix @ ob.matrix_world
    mesh.transform(mat)
    if mat.is_negative:
        mesh.flip_normals()

    vertices = mesh.vertices

    polygons = []
    for polygon in mesh.polygons:
        polygons.append([vertices[index].co.copy() for index in polygon.vertices])

    # retrieve linear elements from objects with no faces

    edges = []
    if not polygons:
        for edge in mesh.edges:
            edges.append([vertices[index].co.copy() for index in edge.vertices])

    mesh_owner.to_mesh_clear()
    return {"polygons": polygons, "edges": edges}


def write_sdnf(filepath, polygons, edges):

    with open(filepath, "w") as data:
        fw = data.write

        # https://help.aveva.com/AVEVA_Everything3D/1.1/SDUVPDMS/wwhelp/wwhimpl/common/html/wwhelp.htm#href=OSUG3.32.05.html&single=true
        # http://catiadoc.free.fr/online/sr1ug_C2/sr1ugat0801.htm

        # 00 Title Packet

        fw("Packet 00\n")
        fw('""\n')
        fw('"My Engineering Company"\n')
        fw('"My Client"\n')
        fw('"My Structure"\n')
        fw('"10/02/13" "16:27:18"\n')
        fw('1 "io_sdnf.py"\n')
        fw('"My Design Code"\n')
        fw("0\n")

        # 10 Linear elements

        fw("Packet 10\n")

        # linear units and number of elements

        fw('"meters" ' + str(len(edges)) + "\n")

        edge_index = 100001
        for item in edges:
            edge = item["edge"]
            section = item["section"]

            # Member number, Cardinal Point, Status, Class, Type, Piece Mark, Revision Number
            # 100001 5 0 0 "beam" "" 0
            fw(str(edge_index) + ' 5 0 0 "beam" "" 0\n')

            edge_index += 1

            # Section Size, Grade, Rotation, Mirror X axis, Mirror Y axis
            # "UC152x152x23" "S355" 0.000000 0 0
            fw('"' + section + '" "S355" 0.000000 0 0\n')

            # Orientation Vector; Start, End Co-ordinates; Start, End Cutbacks
            # 1.000000 0.000000 -0.000000 1000.000000 1000.000000 1000.000000 1000.000000 1000.000000 0.000000 0.000000 0.000000
            if edge[0][0] == edge[1][0] and edge[0][1] == edge[1][1]:
                fw("1.000000 0.000000 0.000000 ")
            else:
                fw("0.000000 0.000000 1.000000 ")
            for vert in edge:
                fw("%f %f %f " % vert[:])
            fw("0.000000 0.000000\n")

            # X, Y Cross-section offsets
            # 0.000000 0.000000
            fw("0.000000 0.000000\n")

            # X, Y, Z Offsets Start; X, Y, Z Offsets End
            # 0.000000 0.000000 0.000000 0.000000 0.000000 0.000000
            fw("0.000000 0.000000 0.000000 0.000000 0.000000 0.000000\n")

            # Releases - End 1 Tx, Ty, Tz, Rx, Ry, Rz; End 2 Tx, Ty, Tz, Rx, Ry, Rz
            # 0 0 0 0 0 0 0 0 0 0 0 0
            fw("0 0 0 0 0 0 0 0 0 0 0 0\n")

        # 20 Plate elements

        fw("Packet 20\n")

        # linear units, thickness units, and number of elements

        fw('"meters" "meters" ' + str(len(polygons)) + "\n")

        face_index = 200001
        for item in polygons:
            face = item["polygon"]
            thickness = item["thickness"]
            offset = item["offset"]

            # 0 = by centre
            # 1 = positive face
            # -1 = negative face
            connect_point = 0
            if offset > 0.99:
                connect_point = -1
            elif offset < -0.99:
                connect_point = 1

            # Member ID; Connect Point; Status; Class; Type
            fw(str(face_index) + " " + str(connect_point) + ' 0 0 "plate"\n')

            # Piece mark; Grade, Thickness, number of nodes
            fw('"" "S355" ' + str("%f" % thickness) + " " + str(len(face)) + "\n")

            for vert in face:
                fw("%f %f %f\n" % vert[:])
            face_index += 1
