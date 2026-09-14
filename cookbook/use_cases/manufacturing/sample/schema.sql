PRAGMA foreign_keys = ON;

CREATE TABLE site (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE work_center (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    site_id INTEGER NOT NULL REFERENCES site(id)
);

CREATE TABLE machine_tool (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    asset_code TEXT NOT NULL,
    machine_type TEXT NOT NULL,
    work_center_id INTEGER REFERENCES work_center(id)
);

CREATE TABLE cutting_tool (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    tool_life_remaining REAL NOT NULL
);

CREATE TABLE fixture (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    fixture_id TEXT NOT NULL
);

CREATE TABLE material (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE part_drawing (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    drawing_no TEXT NOT NULL
);

CREATE TABLE workpiece (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    workpiece_no TEXT NOT NULL,
    material_id INTEGER NOT NULL REFERENCES material(id),
    drawing_id INTEGER NOT NULL REFERENCES part_drawing(id)
);

CREATE TABLE process_plan (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    plan_no TEXT NOT NULL,
    drawing_id INTEGER NOT NULL REFERENCES part_drawing(id)
);

CREATE TABLE process_operation (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    operation_no TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    nc_program TEXT,
    plan_id INTEGER NOT NULL REFERENCES process_plan(id),
    tool_id INTEGER REFERENCES cutting_tool(id),
    fixture_id INTEGER REFERENCES fixture(id)
);

CREATE TABLE work_order (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    work_order_no TEXT NOT NULL,
    plan_id INTEGER NOT NULL REFERENCES process_plan(id),
    workpiece_id INTEGER NOT NULL REFERENCES workpiece(id)
);

CREATE TABLE operator (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE operation_execution (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    work_order_id INTEGER NOT NULL REFERENCES work_order(id),
    operation_id INTEGER NOT NULL REFERENCES process_operation(id),
    machine_id INTEGER NOT NULL REFERENCES machine_tool(id),
    operator_id INTEGER NOT NULL REFERENCES operator(id),
    tool_id INTEGER REFERENCES cutting_tool(id),
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL
);

CREATE TABLE inspection (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    workpiece_id INTEGER NOT NULL REFERENCES workpiece(id),
    result TEXT NOT NULL
);

CREATE TABLE measurement (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    inspection_id INTEGER NOT NULL REFERENCES inspection(id),
    dimension TEXT NOT NULL,
    measured_value REAL NOT NULL,
    spec_min REAL NOT NULL,
    spec_max REAL NOT NULL
);
