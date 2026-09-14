INSERT INTO site (id, name) VALUES (1, '总厂');

INSERT INTO work_center (id, name, code, site_id) VALUES
    (1, '数控铣削工段', 'WC-MILL', 1),
    (2, '数控车削工段', 'WC-TURN', 1);

INSERT INTO machine_tool (id, name, asset_code, machine_type, work_center_id) VALUES
    (1, 'VMC-01', 'VMC-01', 'mill', 1),
    (2, 'CK-02', 'CK-02', 'lathe', 2);

INSERT INTO cutting_tool (id, name, tool_id, tool_life_remaining) VALUES
    (1, 'EM-10', 'EM-10', 80.0),
    (2, 'TN-08', 'TN-08', 50.0);

INSERT INTO fixture (id, name, fixture_id) VALUES
    (1, 'Vise-01', 'FIX-VISE-01');

INSERT INTO material (id, name) VALUES (1, '45钢');

INSERT INTO part_drawing (id, name, drawing_no) VALUES
    (1, '法兰盘', 'DWG-FLANGE-001');

INSERT INTO workpiece (id, name, workpiece_no, material_id, drawing_id) VALUES
    (1, 'WP-1001', 'WP-1001', 1, 1);

INSERT INTO process_plan (id, name, plan_no, drawing_id) VALUES
    (1, '法兰盘工艺', 'PP-FLANGE-A', 1);

INSERT INTO process_operation (id, name, operation_no, sequence_no, nc_program, plan_id, tool_id, fixture_id) VALUES
    (1, '粗铣平面', 'OP10', 10, 'O1001.nc', 1, 1, 1),
    (2, '车外圆', 'OP20', 20, 'O2001.nc', 1, 2, NULL);

INSERT INTO work_order (id, name, work_order_no, plan_id, workpiece_id) VALUES
    (1, '法兰盘工单', 'WO-2026-001', 1, 1);

INSERT INTO operator (id, name) VALUES (1, '张工');

INSERT INTO operation_execution (
    id, name, work_order_id, operation_id, machine_id, operator_id, tool_id, started_at, ended_at
) VALUES (
    1,
    'WO-2026-001/OP10',
    1, 1, 1, 1, 1,
    '2026-09-01T08:00:00',
    '2026-09-01T10:30:00'
);

INSERT INTO inspection (id, name, workpiece_id, result) VALUES
    (1, 'WP-1001终检', 1, 'pass');

INSERT INTO measurement (id, name, inspection_id, dimension, measured_value, spec_min, spec_max) VALUES
    (1, '外径', 1, '外径', 50.02, 49.90, 50.10);
