# -*- coding: utf-8 -*-
"""
Maya顶点吸附工具
使用说明：
    from ModelTools.xiaota import VertexSnapperTool
    from importlib import reload
    reload(VertexSnapperTool)
    VertexSnapperTool.show()
"""

import traceback

import maya.cmds as mc
from maya.api import OpenMaya as om


# ─────────────────────── 工具函数 ───────────────────────

def _selection_to_verts(long=True):
    """把当前选择（顶点/边/面/物体）统一转换成扁平顶点列表"""
    sel = mc.ls(selection=True, flatten=True, long=long) or []
    if not sel:
        return []
    converted = mc.polyListComponentConversion(sel, toVertex=True) or []
    return mc.ls(converted, flatten=True, long=long) or []


def _mesh_world_points(mesh_transform_or_shape):
    """用 OpenMaya 批量取一个 mesh 的全部世界坐标，返回 [(x,y,z), ...]"""
    sel = om.MSelectionList()
    sel.add(mesh_transform_or_shape)
    dag = sel.getDagPath(0)
    dag.extendToShape() if dag.apiType() == om.MFn.kTransform else None
    pts = om.MFnMesh(dag).getPoints(om.MSpace.kWorld)
    return [(p.x, p.y, p.z) for p in pts]


def _vert_world_points(vtx_list):
    """批量取一组 .vtx[i] 的世界坐标，按 mesh 分组以减少 API 调用"""
    by_mesh = {}
    order = []
    for v in vtx_list:
        mesh, idx_str = v.rsplit('.vtx[', 1)
        idx = int(idx_str.rstrip(']'))
        by_mesh.setdefault(mesh, []).append((idx, len(order)))
        order.append(None)
    for mesh, items in by_mesh.items():
        sel = om.MSelectionList()
        sel.add(mesh)
        dag = sel.getDagPath(0)
        if dag.apiType() == om.MFn.kTransform:
            dag.extendToShape()
        pts = om.MFnMesh(dag).getPoints(om.MSpace.kWorld)
        for idx, slot in items:
            p = pts[idx]
            order[slot] = (p.x, p.y, p.z)
    return order


def _nearest_neighbors(target_pts, ref_pts, max_dist=None):
    """对每个 target_pts 找最近 ref_pts，返回 (closest_pos_list, skipped_indices)
    超过 max_dist 的目标点会被跳过。"""
    if not target_pts or not ref_pts:
        return [None] * len(target_pts), list(range(len(target_pts)))

    max_sq = (max_dist * max_dist) if (max_dist is not None and max_dist > 0) else None

    closest = [None] * len(target_pts)
    skipped = []
    for gi, tp in enumerate(target_pts):
        tx, ty, tz = tp
        best_d2 = float('inf')
        best = None
        for rp in ref_pts:
            dx = tx - rp[0]; dy = ty - rp[1]; dz = tz - rp[2]
            d2 = dx * dx + dy * dy + dz * dz
            if d2 < best_d2:
                best_d2 = d2
                best = rp
        if max_sq is not None and best_d2 > max_sq:
            skipped.append(gi)
        else:
            closest[gi] = best
    return closest, skipped

class VertexSnapperUI:
    """Maya顶点吸附工具 - 提供自动和手动两种吸附模式"""
    
    def __init__(self):
        self.window_id = "vertexSnapperUIWindow"
        # source/target 各自为 dict: {"kind": "mesh"|"verts", "value": str | [str, ...]}
        self.source_data = None
        self.target_data = None

        if mc.window(self.window_id, exists=True):
            mc.deleteUI(self.window_id, window=True)
        self.create_ui()

    def create_ui(self):
        """创建主UI界面"""
        self.window = mc.window(self.window_id, title="顶点吸附工具",
                                widthHeight=(280, 260), sizeable=True)
        mc.columnLayout(adjustableColumn=True, rowSpacing=8,
                        columnOffset=('both', 8))
        mc.separator(height=4, style='none')

        self._frame("源 (提供位置)")
        self._load_clear_row("加载源模型/顶点", self.load_source, self.clear_source)
        self.source_field = mc.textField(placeholderText="未加载源", editable=False)
        mc.setParent('..'); mc.setParent('..')

        self._frame("目标 (要移动顶点)")
        self._load_clear_row("加载目标模型/顶点", self.load_target, self.clear_target)
        self.target_field = mc.textField(placeholderText="未加载目标", editable=False)
        mc.setParent('..'); mc.setParent('..')

        self._frame("选项")
        self._options_row()
        mc.button(label="执行吸附", command=self.execute_snap, height=34,
                  backgroundColor=(0.40, 0.55, 0.40))
        mc.setParent('..'); mc.setParent('..')

        mc.separator(height=4, style='none')
        mc.showWindow(self.window)

    def _load_clear_row(self, load_label, load_cmd, clear_cmd):
        """加载 + 清除 的自适应宽度按钮行（加载键随窗口拉伸，清除键固定）"""
        mc.rowLayout(numberOfColumns=2, adjustableColumn=1,
                     columnAttach=[(1, 'both', 0), (2, 'both', 4)])
        mc.button(label=load_label, command=load_cmd, height=28)
        mc.button(label="清除", width=52, command=clear_cmd, height=28)
        mc.setParent('..')

    def _frame(self, label):
        """统一样式的分组框"""
        mc.frameLayout(label=label, collapsable=False, marginHeight=8, marginWidth=8)
        mc.columnLayout(adjustableColumn=True, rowSpacing=6)

    def _options_row(self):
        """选项行：同拓扑勾选 + 最大距离（勾选时最大距离灰显）"""
        mc.rowLayout(numberOfColumns=2, adjustableColumn=2,
                     columnAttach=[(1, 'both', 0), (2, 'both', 8)])
        self.order_check = mc.checkBox(
            label="同拓扑模式", value=True,
            changeCommand=self._on_order_toggled,
            annotation="勾选：第 N 个目标顶点 → 第 N 个源顶点 (要求两边顶点数相同)。"
                       "不勾选：每个目标顶点吸附到最近的源顶点。")
        self.max_dist_field = mc.floatFieldGrp(
            label="最大距离", numberOfFields=1, value1=0.0,
            columnWidth2=(56, 70), precision=3,
            annotation="距离阈值，超过则跳过该目标顶点。0 = 不限制。仅在未勾选「同拓扑模式」时生效。")
        mc.setParent('..')
        # 初始为勾选，最大距离应灰显
        self._on_order_toggled(True)

    def _on_order_toggled(self, value):
        """切换同拓扑模式时，灰化/启用最大距离输入框"""
        mc.floatFieldGrp(self.max_dist_field, edit=True, enable=not value)

    # ─────────── 加载 / 清除 ───────────

    def _resolve_selection(self):
        """把当前选择归一化成 ('mesh', mesh_long) 或 ('verts', [vtx, ...]) 或 None"""
        sel = mc.ls(selection=True, long=True) or []
        if not sel:
            return None

        comp_kinds = ('.vtx[', '.e[', '.f[', '.map[')
        if any(k in s for s in sel for k in comp_kinds):
            verts = _selection_to_verts()
            return ('verts', verts) if verts else None

        transforms = mc.ls(sel, type='transform', long=True) or []
        if len(transforms) == 1:
            shapes = mc.listRelatives(transforms[0], shapes=True, type='mesh', path=True)
            if shapes:
                return ('mesh', transforms[0])
        return None

    def _describe(self, data):
        if data is None:
            return ""
        kind, value = data["kind"], data["value"]
        if kind == "mesh":
            return "模型: {}".format(value.split('|')[-1])
        return "顶点: {} 个".format(len(value))

    def _load_into(self, slot_attr, field_attr, label):
        resolved = self._resolve_selection()
        if not resolved:
            mc.warning(f"请选择一个网格物体或顶点/边/面作为{label}。")
            return
        kind, value = resolved
        if kind == "mesh" and len(value) == 0:
            return
        if kind == "verts" and not value:
            return
        setattr(self, slot_attr, {"kind": kind, "value": value})
        text = self._describe(getattr(self, slot_attr))
        mc.textField(getattr(self, field_attr), edit=True, text=text)
        print(f"已加载{label} - {text}")

    def load_source(self, *args):
        self._load_into("source_data", "source_field", "源")

    def clear_source(self, *args):
        self.source_data = None
        mc.textField(self.source_field, edit=True, text="", placeholderText="未加载源")

    def load_target(self, *args):
        self._load_into("target_data", "target_field", "目标")

    def clear_target(self, *args):
        self.target_data = None
        mc.textField(self.target_field, edit=True, text="", placeholderText="未加载目标")

    # ─────────── 执行 ───────────

    def _resolve_positions(self, data, label):
        """data → (verts_list_or_None, world_positions_list)"""
        kind, value = data["kind"], data["value"]
        if kind == "mesh":
            if not mc.objExists(value):
                mc.warning(f"{label}模型已被删除，请重新加载。")
                return None, None
            return None, _mesh_world_points(value)
        # verts
        alive = [v for v in value if mc.objExists(v)]
        if not alive:
            mc.warning(f"{label}顶点已被删除，请重新加载。")
            return None, None
        return alive, _vert_world_points(alive)

    def _target_verts(self, data):
        """目标必须是顶点列表（mesh 转为其全部顶点）"""
        kind, value = data["kind"], data["value"]
        if kind == "verts":
            return [v for v in value if mc.objExists(v)]
        if not mc.objExists(value):
            return []
        shape = mc.listRelatives(value, shapes=True, type='mesh', path=True, fullPath=True)
        if not shape:
            return []
        count = mc.polyEvaluate(value, vertex=True)
        return mc.ls(f"{value}.vtx[0:{count - 1}]", flatten=True, long=True) or []

    def execute_snap(self, *args):
        if not self.source_data:
            mc.warning("请先加载源（模型或顶点）。")
            return
        if not self.target_data:
            mc.warning("请先加载目标（模型或顶点）。")
            return

        _, ref_positions = self._resolve_positions(self.source_data, "源")
        if ref_positions is None:
            return

        target_verts = self._target_verts(self.target_data)
        if not target_verts:
            mc.warning("目标顶点为空或已被删除，请重新加载。")
            return

        by_order = mc.checkBox(self.order_check, query=True, value=True)
        if by_order:
            if len(ref_positions) != len(target_verts):
                mc.warning("同拓扑模式要求源/目标顶点数量相等：源 {} 个，目标 {} 个。".format(
                    len(ref_positions), len(target_verts)))
                return
            self._perform_snap_logic(target_verts, ref_positions, paired=True)
        else:
            max_dist = mc.floatFieldGrp(self.max_dist_field, query=True, value1=True)
            self._perform_snap_logic(target_verts, ref_positions, max_dist=max_dist)

    def _perform_snap_logic(self, verts_to_move, reference_positions, max_dist=None, paired=False):
        """执行顶点吸附的核心逻辑。
        paired=True 时按 index 一一对应；否则对每个目标顶点找最近源顶点。
        max_dist>0 时跳过超过该距离的目标顶点（仅最近邻模式）。"""
        verts = [v for v in verts_to_move if mc.objExists(v)]
        if not verts:
            mc.warning("未处理任何有效的顶点。")
            return

        if paired:
            targets = reference_positions[:len(verts)]
            skipped = []
        else:
            target_positions = _vert_world_points(verts)
            targets, skipped = _nearest_neighbors(target_positions, reference_positions, max_dist=max_dist)

        moved = 0
        opened = False
        try:
            mc.undoInfo(openChunk=True)
            opened = True
            for vtx, dest in zip(verts, targets):
                if dest is None:
                    continue
                mc.move(dest[0], dest[1], dest[2], vtx, worldSpace=True, absolute=True)
                moved += 1
        except Exception:
            mc.warning("吸附过程中发生错误，详见 Script Editor。")
            print(traceback.format_exc())
        finally:
            if opened:
                mc.undoInfo(closeChunk=True)

        msg = "吸附完成：移动 {} 个顶点".format(moved)
        if skipped:
            msg += "，跳过 {} 个（超出最大距离）".format(len(skipped))
        if moved == 0:
            mc.warning(msg)
        else:
            print(msg)
            try:
                mc.inViewMessage(amg=msg, pos="midCenter", fade=True)
            except RuntimeError:
                pass

# 全局函数，用于启动工具
def show():
    """启动顶点吸附工具"""
    global vertex_snapper_tool
    vertex_snapper_tool = VertexSnapperUI()
    return vertex_snapper_tool

# 如果直接运行此文件
if __name__ == "__main__":
    show()
