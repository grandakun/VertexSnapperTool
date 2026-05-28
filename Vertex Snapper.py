# -*- coding: utf-8 -*-
"""
Maya顶点吸附工具
使用说明：
1. 将此文件保存为 vertex_snapper.py
2. 放到 Maya 的 scripts 文件夹中
3. 在Maya Script Editor中运行以下代码启动工具：

import vertex_snapper
reload(vertex_snapper)
vertex_snapper.show()

或者创建Shelf按钮，使用上面3行代码
"""

import maya.cmds as mc

class VertexSnapperUI:
    """Maya顶点吸附工具 - 提供自动和手动两种吸附模式"""
    
    def __init__(self):
        self.window_id = "vertexSnapperUIWindow"
        self.reference_model = None
        self.verts_to_move = []
        self.reference_verts = []

        if mc.window(self.window_id, exists=True):
            mc.deleteUI(self.window_id, window=True)
        self.create_ui()

    def create_ui(self):
        """创建主UI界面"""
        self.window = mc.window(self.window_id, title="顶点吸附工具", widthHeight=(360, 380), sizeable=True)
        main_layout = mc.columnLayout(adjustableColumn=True, rowSpacing=5)
        tabs = mc.tabLayout(innerMarginWidth=5, innerMarginHeight=5)
        self._create_auto_snap_tab(tabs)
        self._create_manual_snap_tab(tabs)
        mc.tabLayout(tabs, edit=True, tabLabel=((self.auto_snap_tab, '自动吸附'), (self.manual_snap_tab, '手动吸附')))
        mc.showWindow(self.window)

    def _create_auto_snap_tab(self, parent):
        """创建自动吸附标签页"""
        self.auto_snap_tab = mc.columnLayout(adjustableColumn=True, rowSpacing=10, parent=parent)
        mc.frameLayout(label="步骤1: 设置源模型 (提供参考位置)", collapsable=False, marginHeight=10, marginWidth=5)
        mc.columnLayout(adjustableColumn=True)
        mc.button(label="加载选中物体为源模型", command=self.load_auto_source_model, height=40)
        self.auto_source_field = mc.textField(placeholderText="未加载源模型...", editable=False)
        mc.setParent('..')
        mc.setParent('..')
        mc.separator(height=10, style='in')
        mc.frameLayout(label="步骤2: 选择目标顶点并执行吸附", collapsable=False, marginHeight=10, marginWidth=5)
        mc.columnLayout(adjustableColumn=True)
        mc.text(label="选择要移动的顶点，点击按钮执行吸附", align="left")
        mc.button(label="吸附选中顶点到源模型", command=self.execute_auto_snap, height=40, backgroundColor=(0.4, 0.6, 0.4))
        mc.setParent('..')
        mc.setParent('..')
        mc.setParent(parent)

    def _create_manual_snap_tab(self, parent):
        """创建手动吸附标签页"""
        self.manual_snap_tab = mc.columnLayout(adjustableColumn=True, rowSpacing=10, parent=parent)
        mc.frameLayout(label="步骤1: 加载源顶点 (提供目标位置)", collapsable=False, marginHeight=10, marginWidth=5)
        mc.rowLayout(numberOfColumns=2, columnWidth2=(270, 70))
        mc.button(label="加载源顶点", command=self.load_manual_reference_verts, height=40)
        mc.button(label="清除", command=self.clear_manual_reference_verts)
        mc.setParent('..')
        self.reference_vtx_field = mc.textField(placeholderText="未加载源顶点...", editable=False)
        mc.setParent('..')
        mc.frameLayout(label="步骤2: 加载目标顶点 (要移动的顶点)", collapsable=False, marginHeight=10, marginWidth=5)
        mc.rowLayout(numberOfColumns=2, columnWidth2=(270, 70))
        mc.button(label="加载目标顶点", command=self.load_manual_verts_to_move, height=40)
        mc.button(label="清除", command=self.clear_manual_verts_to_move)
        mc.setParent('..')
        self.verts_to_move_field = mc.textField(placeholderText="未加载目标顶点...", editable=False)
        mc.setParent('..')
        mc.separator(height=15, style='in')
        mc.button(label="执行吸附", command=self.execute_manual_snap, height=40, backgroundColor=(0.4, 0.5, 0.65))
        mc.setParent(parent)

    def load_auto_source_model(self, *args):
        """加载源模型（自动模式）"""
        selection = mc.ls(selection=True, type='transform', long=True)
        if not selection:
            mc.warning("请选择一个网格物体作为源模型。")
            return
        if len(selection) > 1:
            mc.warning("请只选择一个物体作为源模型。")
            return
        source_model = selection[0]
        shapes = mc.listRelatives(source_model, shapes=True, type='mesh', path=True)
        if not shapes:
            mc.warning(f"'{source_model}' 不是一个有效的网格物体。")
            return
        self.reference_model = source_model
        display_name = self.reference_model.split('|')[-1]
        mc.textField(self.auto_source_field, edit=True, text=display_name)
        print(f"已加载源模型: {display_name}")

    def execute_auto_snap(self, *args):
        """执行自动吸附"""
        if not self.reference_model or not mc.objExists(self.reference_model):
            mc.warning("未设置源模型或源模型已被删除，请重新加载。")
            return
        target_verts = [v for v in mc.ls(selection=True, flatten=True, long=True) if '.vtx[' in v]
        if not target_verts:
            mc.warning("请选择要移动的目标顶点。")
            return
        source_verts = mc.ls(f'{self.reference_model}.vtx[*]', flatten=True, long=True)
        reference_positions = [mc.xform(v, query=True, translation=True, worldSpace=True) for v in source_verts]
        self._perform_snap_logic(target_verts, reference_positions)

    def load_manual_reference_verts(self, *args):
        """加载源顶点（手动模式）"""
        self.reference_verts = [v for v in mc.ls(selection=True, flatten=True, long=True) if '.vtx[' in v]
        count = len(self.reference_verts)
        if count > 0:
            mc.textField(self.reference_vtx_field, edit=True, text=f"已加载 {count} 个源顶点")
            print(f"已加载 {count} 个源顶点")
        else:
            mc.warning("未选择任何顶点。")
        
    def clear_manual_reference_verts(self, *args):
        """清除源顶点"""
        self.reference_verts = []
        mc.textField(self.reference_vtx_field, edit=True, text="", placeholderText="未加载源顶点...")

    def load_manual_verts_to_move(self, *args):
        """加载目标顶点（手动模式）"""
        self.verts_to_move = [v for v in mc.ls(selection=True, flatten=True, long=True) if '.vtx[' in v]
        count = len(self.verts_to_move)
        if count > 0:
            mc.textField(self.verts_to_move_field, edit=True, text=f"已加载 {count} 个目标顶点")
            print(f"已加载 {count} 个目标顶点")
        else:
            mc.warning("未选择任何顶点。")

    def clear_manual_verts_to_move(self, *args):
        """清除目标顶点"""
        self.verts_to_move = []
        mc.textField(self.verts_to_move_field, edit=True, text="", placeholderText="未加载目标顶点...")
    
    def execute_manual_snap(self, *args):
        """执行手动吸附"""
        if not self.reference_verts:
            mc.warning("未加载源顶点，请先执行步骤1。")
            return
        if not self.verts_to_move:
            mc.warning("未加载目标顶点，请先执行步骤2。")
            return
        if not mc.objExists(self.reference_verts[0]):
            mc.warning("源顶点已被删除，请重新加载。")
            return
        if not mc.objExists(self.verts_to_move[0]):
            mc.warning("目标顶点已被删除，请重新加载。")
            return
        reference_positions = [mc.xform(v, query=True, translation=True, worldSpace=True) for v in self.reference_verts]
        self._perform_snap_logic(self.verts_to_move, reference_positions)

    def _perform_snap_logic(self, verts_to_move, reference_positions):
        """执行顶点吸附的核心逻辑"""
        try:
            mc.undoInfo(openChunk=True)
            processed_count = 0
            for vtx_to_move in verts_to_move:
                if not mc.objExists(vtx_to_move):
                    continue
                current_pos = mc.xform(vtx_to_move, query=True, translation=True, worldSpace=True)
                min_distance_squared = float('inf')
                closest_ref_pos = None
                for ref_pos in reference_positions:
                    dist_sq = sum([(a - b) ** 2 for a, b in zip(current_pos, ref_pos)])
                    if dist_sq < min_distance_squared:
                        min_distance_squared = dist_sq
                        closest_ref_pos = ref_pos
                if closest_ref_pos:
                    mc.move(closest_ref_pos[0], closest_ref_pos[1], closest_ref_pos[2], vtx_to_move, worldSpace=True, absolute=True)
                    processed_count += 1
            if processed_count > 0:
                print(f"✓ 吸附完成！成功移动了 {processed_count} 个顶点。")
            else:
                mc.warning("未处理任何有效的顶点。")
        except Exception as e:
            mc.error(f"吸附过程中发生错误: {str(e)}")
        finally:
            mc.undoInfo(closeChunk=True)

# 全局函数，用于启动工具
def show():
    """启动顶点吸附工具"""
    global vertex_snapper_tool
    try:
        vertex_snapper_tool
    except:
        pass
    else:
        try:
            if mc.window(vertex_snapper_tool.window_id, exists=True):
                mc.deleteUI(vertex_snapper_tool.window_id, window=True)
        except:
            pass
    vertex_snapper_tool = VertexSnapperUI()
    return vertex_snapper_tool

# 如果直接运行此文件
if __name__ == "__main__":
    show()
