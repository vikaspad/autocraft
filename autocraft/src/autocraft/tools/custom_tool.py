"""
custom_tool.py for the "autocraft" project (CrewAI)

This module defines a collection of custom tools referenced by agents.yaml:
- PomXmlTool
- JavaCodegenTool
- FileWriterTool
- RepoScaffolderTool
- ReadmeWriterTool
- H2RunnerTool
- JDBCExecutorTool
- MongoEmbedTool
- TestcontainersTool
- KafkaMockTool
- OpenAPISchemaTool
- FakerTool
- KafkaMessagingScaffoldTool
- EmsMessagingScaffoldTool

Each tool subclasses `BaseTool` from `crewai_tools` and exposes a simple, typed interface
that CrewAI can invoke from `crew.py`. All tools are synchronous; async is deliberately
not implemented to keep behavior deterministic inside Crew runs.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union, ClassVar
from pydantic import BaseModel, Field, field_validator


import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Type, ClassVar, Any, Dict, List, Optional, Union

from crewai.tools import BaseTool

from pydantic import BaseModel, Field, field_validator


# -----------------------------
# Utilities
# -----------------------------

def _ensure_parent_dirs(path: Union[str, Path]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _write_file(path: Union[str, Path], content: str, overwrite: bool = True) -> str:
    path = Path(path)
    _ensure_parent_dirs(path)
    if path.exists() and not overwrite:
        return f"[SKIPPED] {path} already exists"
    path.write_text(content, encoding="utf-8")
    return f"[WROTE] {path} ({len(content)} bytes)"


def _normalize_package_to_path(base_package: str) -> str:
    return base_package.strip().replace(".", "/")


def _read_template(template_name: str) -> str:
    """Read template content from templates directory."""
    template_path = Path(__file__).parent.parent / "templates" / template_name
    if template_path.exists():
        return template_path.read_text(encoding="utf-8").strip()
    return ""


# -----------------------------
# FileWriterTool
# -----------------------------

class FileWriterArgs(BaseModel):
    path: str = Field(..., description="Filesystem path to write, relative to repo root")
    content: str = Field(..., description="Full file contents")
    overwrite: bool = Field(True, description="If false, will skip when file exists")


class FileWriterTool(BaseTool):
    name: str = "FileWriterTool"
    description: str = "Writes text content to a file. Creates directories as needed."
    #args_schema: ClassVar[type[BaseModel]] = FileWriterArgs

    def _run(self, path: str, content: str, overwrite: bool = True) -> str:
        return _write_file(path, content, overwrite)


# -----------------------------
# RepoScaffolderTool
# -----------------------------

class RepoScaffolderArgs(BaseModel):
    base_dir: str = Field(".", description="Base directory for the project")
    # Common defaults target a standard Java Maven layout
    include_defaults: bool = Field(True, description="Include standard Maven/Java skeleton")
    extra_paths: List[str] = Field(default_factory=list, description="Additional directories/files to create")


DEFAULT_SCAFFOLD = [
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "README.md",
    "docs/",
    "docs/USAGE.md",
    "docs/ARCHITECTURE.md",
    "pom.xml",
    "src/main/java/",
    "src/test/java/",
    "src/main/resources/",
    "src/test/resources/",
]


class RepoScaffolderTool(BaseTool):
    name: str = "RepoScaffolderTool"
    description: str = "Creates a Java/Maven project skeleton and any additional paths."
    #args_schema: ClassVar[type[BaseModel]] = RepoScaffolderArgs

    def _run(self, base_dir: str = ".", include_defaults: bool = True, extra_paths: Optional[List[str]] = None) -> str:
        base = Path(base_dir)
        base.mkdir(parents=True, exist_ok=True)
        created: List[str] = []

        paths = list(extra_paths or [])
        if include_defaults:
            paths = list(dict.fromkeys(DEFAULT_SCAFFOLD + paths))  # dedupe, keep order

        for p in paths:
            target = base / p
            if p.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                created.append(f"[DIR] {target}")
            else:
                _ensure_parent_dirs(target)
                if not target.exists():
                    target.write_text("", encoding="utf-8")
                    created.append(f"[FILE] {target}")
                else:
                    created.append(f"[SKIP] {target} exists")
        return "\n".join(created)


# -----------------------------
# PomXmlTool
# -----------------------------

class PomDependency(BaseModel):
    groupId: str
    artifactId: str
    version: Optional[str] = None
    scope: Optional[str] = None
    optional: Optional[bool] = None

class PomPlugin(BaseModel):
    groupId: str
    artifactId: str
    version: Optional[str] = None
    configuration_xml: Optional[str] = Field(default=None, description="Raw XML for <configuration>...</configuration> block")
    executions_xml: Optional[str] = Field(default=None, description="Raw XML for <executions>...</executions> block")

class PomArgs(BaseModel):
    base_dir: str = Field(".", description="Repo root where pom.xml will be placed or updated")
    groupId: str = Field("com.example", description="Maven groupId")
    artifactId: str = Field("qa-testkit", description="Maven artifactId")
    version: str = Field("0.1.0", description="Project version")
    java_version: str = Field("17", description="Target Java version")
    dependencies: List[PomDependency] = Field(default_factory=list, description="List of dependencies")
    plugins: List[PomPlugin] = Field(default_factory=list, description="List of build plugins")
    packaging: str = Field("jar", description="Maven packaging")

class PomXmlTool(BaseTool):
    name: str = "PomXmlTool"
    description: str = "Generates a minimal, opinionated Maven pom.xml with optional deps/plugins."
    #args_schema: ClassVar[type[BaseModel]] = PomArgs

    def _run(
        self,
        base_dir: str = ".",
        groupId: str = "com.example",
        artifactId: str = "qa-testkit",
        version: str = "0.1.0",
        java_version: str = "17",
        dependencies: Optional[List[Dict[str, Any]]] = None,
        plugins: Optional[List[Dict[str, Any]]] = None,
        packaging: str = "jar",
    ) -> str:
        deps_xml = ""
        for dep in (dependencies or []):
            optional = f"\n      <optional>{str(dep.get('optional')).lower()}</optional>" if dep.get("optional") is not None else ""
            scope = f"\n      <scope>{dep.get('scope')}</scope>" if dep.get("scope") else ""
            version_tag = f"\n      <version>{dep.get('version')}</version>" if dep.get("version") else ""
            deps_xml += f"""
        <dependency>
        <groupId>{dep['groupId']}</groupId>
        <artifactId>{dep['artifactId']}</artifactId>{version_tag}{scope}{optional}
        </dependency>"""

            plugins_xml = ""
            for plg in (plugins or []):
                ver = f"\n        <version>{plg.get('version')}</version>" if plg.get("version") else ""
                config = f"\n        {plg.get('configuration_xml')}" if plg.get("configuration_xml") else ""
                execs = f"\n        {plg.get('executions_xml')}" if plg.get("executions_xml") else ""
                plugins_xml += f"""
        <plugin>
            <groupId>{plg['groupId']}</groupId>
            <artifactId>{plg['artifactId']}</artifactId>{ver}{config}{execs}
        </plugin>"""

            xml = f"""<project xmlns="http://maven.apache.org/POM/4.0.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
            <modelVersion>4.0.0</modelVersion>

            <groupId>{groupId}</groupId>
            <artifactId>{artifactId}</artifactId>
            <version>{version}</version>
            <packaging>{packaging}</packaging>

            <properties>
                <maven.compiler.source>{java_version}</maven.compiler.source>
                <maven.compiler.target>{java_version}</maven.compiler.target>
                <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
                <junit.jupiter.version>5.10.2</junit.jupiter.version>
                <assertj.version>3.25.3</assertj.version>
                <mockito.version>5.12.0</mockito.version>
            </properties>

            <dependencies>{deps_xml if deps_xml.strip() else ""}
                <!-- Baseline testing stack -->
                <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${{junit.jupiter.version}}</version>
                <scope>test</scope>
                </dependency>
                <dependency>
                <groupId>org.assertj</groupId>
                <artifactId>assertj-core</artifactId>
                <version>${{assertj.version}}</version>
                <scope>test</scope>
                </dependency>
                <dependency>
                <groupId>org.mockito</groupId>
                <artifactId>mockito-core</artifactId>
                <version>${{mockito.version}}</version>
                <scope>test</scope>
                </dependency>
            </dependencies>

            <build>
                <plugins>{plugins_xml if plugins_xml.strip() else ""}
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.2.5</version>
                    <configuration>
                    <useModulePath>false</useModulePath>
                    <includes>
                        <include>**/*Test.java</include>
                    </includes>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.jacoco</groupId>
                    <artifactId>jacoco-maven-plugin</artifactId>
                    <version>0.8.11</version>
                    <executions>
                    <execution>
                        <goals>
                        <goal>prepare-agent</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>report</id>
                        <phase>test</phase>
                        <goals>
                        <goal>report</goal>
                        </goals>
                    </execution>
                    </executions>
                </plugin>
                </plugins>
            </build>
            </project>
            """.strip() + "\n"

        out = Path(base_dir) / "pom.xml"
        return _write_file(out, xml, overwrite=True)


# -----------------------------
# JavaCodegenTool
# -----------------------------

class JavaCodegenArgs(BaseModel):
    base_package: str = Field(..., description="Root Java package, e.g., com.example.qatestkit")
    class_name: str = Field(..., description="Java class or test name without .java")
    src_type: str = Field("test", description="Either 'main' or 'test'")
    body: str = Field(..., description="The Java class body between braces")
    imports: List[str] = Field(default_factory=list, description="Optional import statements")
    annotations: List[str] = Field(default_factory=list, description="Optional annotations before class declaration")
    javadoc: Optional[str] = Field(default=None, description="Optional Javadoc for the class")
    base_dir: str = Field(".", description="Repo root where /src/... will be created")

    @field_validator("src_type")
    @classmethod
    def _check_src_type(cls, v: str) -> str:
        if v not in {"main", "test"}:
            raise ValueError("src_type must be 'main' or 'test'")
        return v

# JavaCodegenTool to generate Java classes and tests
class JavaCodegenTool(BaseTool):
    name: str = "JavaCodegenTool"
    description: str = "Writes a Java class or test to the appropriate src path based on base_package and src_type."
    #args_schema: ClassVar[type[BaseModel]] = JavaCodegenArgs

    def _run(
        self,
        base_package: str,
        class_name: str,
        src_type: str = "test",
        body: str = "",
        imports: Optional[List[str]] = None,
        annotations: Optional[List[str]] = None,
        javadoc: Optional[str] = None,
        base_dir: str = ".",
    ) -> str:
        src_root = f"src/{'test' if src_type=='test' else 'main'}/java"
        pkg_path = _normalize_package_to_path(base_package)
        full_dir = Path(base_dir) / src_root / pkg_path
        full_dir.mkdir(parents=True, exist_ok=True)
        path = full_dir / f"{class_name}.java"

        lines: List[str] = [f"package {base_package};", ""]
        for imp in (imports or []):
            lines.append(f"import {imp};")
        if imports:
            lines.append("")

        if javadoc:
            lines.append("/**")
            for line in javadoc.splitlines():
                lines.append(f" * {line}")
            lines.append(" */")

        for ann in (annotations or []):
            lines.append(ann)

        lines.append(f"public class {class_name} " + "{")
        if body:
            for ln in body.splitlines():
                lines.append(f"    {ln}")
        lines.append("}")
        content = "\n".join(lines) + "\n"
        return _write_file(path, content, overwrite=True)


# -----------------------------
# ReadmeWriterTool
# -----------------------------

class ReadmeArgs(BaseModel):
    title: str = Field("QA Testkit", description="Project title")
    sections: Dict[str, str] = Field(default_factory=dict, description="Mapping of heading -> markdown content")
    base_dir: str = Field(".", description="Repo root")


class ReadmeWriterTool(BaseTool):
    name: str = "ReadmeWriterTool"
    description: str = "Generates a README.md with given sections."
    #args_schema: ClassVar[type[BaseModel]] = ReadmeArgs

    def _run(self, title: str = "QA Testkit", sections: Optional[Dict[str, str]] = None, base_dir: str = ".") -> str:
        md_lines = [f"# {title}", ""]
        for h, md in (sections or {}).items():
            md_lines.append(f"## {h}")
            md_lines.append(md.strip())
            md_lines.append("")
        content = "\n".join(md_lines)
        return _write_file(Path(base_dir) / "README.md", content, overwrite=True)


# -----------------------------
# H2RunnerTool
# -----------------------------

class H2RunnerArgs(BaseModel):
    base_package: str = Field(..., description="Root Java package for placement")
    class_name: str = Field("H2SmokeTest", description="Test class name")
    base_dir: str = Field(".", description="Repo root")
    mode: str = Field("testcontainers", description="Either 'testcontainers' or 'inmem'")


H2_TEST_BODY_TESTCONTAINERS = _read_template("H2_TEST_BODY_TESTCONTAINERS.j2")

H2_TEST_BODY_INMEM = _read_template("H2_TEST_BODY_INMEM.j2")

class H2RunnerTool(BaseTool):
    name: str = "H2RunnerTool"
    description: str = "Generates a JUnit test that brings up H2 (in-memory) or a containerized DB and runs a simple query."
    #args_schema: ClassVar[type[BaseModel]] = H2RunnerArgs

    def _run(self, base_package: str, class_name: str = "H2SmokeTest", base_dir: str = ".", mode: str = "testcontainers") -> str:
        body = H2_TEST_BODY_TESTCONTAINERS if mode == "testcontainers" else H2_TEST_BODY_INMEM
        return JavaCodegenTool()._run(
            base_package=base_package,
            class_name=class_name,
            src_type="test",
            body=body,
            imports=[
                "java.sql.*",
                "org.assertj.core.api.Assertions",
                "org.junit.jupiter.api.*",
                "org.testcontainers.containers.*" if mode == "testcontainers" else ""
            ],
            javadoc="Auto-generated smoke test for DB connectivity.",
            base_dir=base_dir,
        )


# -----------------------------
# JDBCExecutorTool
# -----------------------------

class JDBCExecArgs(BaseModel):
    base_package: str
    class_name: str = "JdbcExec"
    base_dir: str = "."
    driver_class: str = Field("org.h2.Driver", description="JDBC driver FQCN")
    jdbc_url: str = Field(..., description="JDBC URL")
    username: str = Field("sa", description="DB username")
    password: str = Field("", description="DB password")
    sql: str = Field("SELECT 1", description="SQL to run in example main()")


JDBC_EXEC_BODY_TMPL = _read_template("JDBC_EXEC_BODY_TMPL.j2")

class JDBCExecutorTool(BaseTool):
    name: str = "JDBCExecutorTool"
    description: str = "Creates a tiny Java 'main' program that connects via JDBC and executes a query."
    #args_schema: ClassVar[type[BaseModel]] = JDBCExecArgs

    def _run(self, base_package: str, jdbc_url: str, class_name: str = "JdbcExec", base_dir: str = ".", driver_class: str = "org.h2.Driver", username: str = "sa", password: str = "", sql: str = "SELECT 1") -> str:
        body = (JDBC_EXEC_BODY_TMPL
                .replace("%DRIVER%", driver_class)
                .replace("%URL%", jdbc_url)
                .replace("%USER%", username)
                .replace("%PASS%", password)
                .replace("%SQL%", sql))
        return JavaCodegenTool()._run(
            base_package=base_package,
            class_name=class_name,
            src_type="main",
            body=body,
            imports=["java.sql.*"],
            javadoc="Auto-generated JDBC example application.",
            base_dir=base_dir,
        )


# -----------------------------
# MongoEmbedTool
# -----------------------------

class MongoEmbedArgs(BaseModel):
    base_package: str
    class_name: str = "MongoEmbedTest"
    base_dir: str = "."


MONGO_EMBED_BODY = _read_template("MONGO_EMBED_BODY.j2")

class MongoEmbedTool(BaseTool):
    name: str = "MongoEmbedTool"
    description: str = "Creates a JUnit test that starts an embedded MongoDB and verifies basic CRUD."
    #args_schema: ClassVar[type[BaseModel]] = MongoEmbedArgs

    def _run(self, base_package: str, class_name: str = "MongoEmbedTest", base_dir: str = ".") -> str:
        return JavaCodegenTool()._run(
            base_package=base_package,
            class_name=class_name,
            src_type="test",
            body=MONGO_EMBED_BODY,
            imports=[
                "org.junit.jupiter.api.*",
                "org.assertj.core.api.Assertions",
                "com.mongodb.client.*",
                "org.bson.Document",
                "de.flapdoodle.embed.mongo.*",
                "de.flapdoodle.embed.mongo.config.*",
                "de.flapdoodle.embed.mongo.distribution.*",
            ],
            javadoc="Auto-generated embedded Mongo test using flapdoodle.",
            base_dir=base_dir,
        )


# -----------------------------
# TestcontainersTool
# -----------------------------

class TestcontainersArgs(BaseModel):
    base_package: str
    class_name: str = "SqlServerContainerTest"
    base_dir: str = "."
    image: str = Field("mcr.microsoft.com/mssql/server:2022-latest", description="Container image")

# TestcontainersSQLServerBody to generate a JUnit test that boots a Testcontainers DB (default SQL Server) and verifies connectivity.
TESTCONTAINERS_SQLSERVER_BODY = _read_template("TESTCONTAINERS_SQLSERVER_BODY.j2")

class TestcontainersTool(BaseTool):
    name: str = "TestcontainersTool"
    description: str = "Generates a JUnit test that boots a Testcontainers DB (default SQL Server) and verifies connectivity."
    #args_schema: ClassVar[type[BaseModel]] = TestcontainersArgs

    def _run(self, base_package: str, class_name: str = "SqlServerContainerTest", base_dir: str = ".", image: str = "mcr.microsoft.com/mssql/server:2022-latest") -> str:
        body = TESTCONTAINERS_SQLSERVER_BODY.replace("%IMAGE%", image)
        return JavaCodegenTool()._run(
            base_package=base_package,
            class_name=class_name,
            src_type="test",
            body=body,
            imports=[
                "java.sql.*",
                "org.assertj.core.api.Assertions",
                "org.junit.jupiter.api.*",
                "org.testcontainers.containers.*",
            ],
            javadoc="Auto-generated Testcontainers-based SQL Server smoke test.",
            base_dir=base_dir,
        )


# -----------------------------
# KafkaMockTool
# -----------------------------

class KafkaMockArgs(BaseModel):
    base_package: str
    class_name: str = "KafkaMockTest"
    base_dir: str = "."


KAFKA_MOCK_BODY = _read_template("KAFKA_MOCK_BODY.h2")

class KafkaMockTool(BaseTool):
    name: str = "KafkaMockTool"
    description: str = "Creates a unit test that demonstrates Kafka MockProducer usage."
    #args_schema: ClassVar[type[BaseModel]] = KafkaMockArgs

    def _run(self, base_package: str, class_name: str = "KafkaMockTest", base_dir: str = ".") -> str:
        return JavaCodegenTool()._run(
            base_package=base_package,
            class_name=class_name,
            src_type="test",
            body=KAFKA_MOCK_BODY,
            imports=[
                "org.junit.jupiter.api.*",
                "org.assertj.core.api.Assertions",
                "org.apache.kafka.clients.producer.*",
            ],
            javadoc="Auto-generated Kafka mock producer test.",
            base_dir=base_dir,
        )


# -----------------------------
# OpenAPISchemaTool
# -----------------------------

class Endpoint(BaseModel):
    method: str = Field(..., description="HTTP method, e.g., GET, POST")
    path: str = Field(..., description="/resource path")
    operationId: Optional[str] = Field(None, description="Optional operationId")
    summary: Optional[str] = None
    requestSchema: Optional[Dict[str, Any]] = Field(default=None, description="JSON Schema for request body")
    responseSchema: Optional[Dict[str, Any]] = Field(default=None, description="JSON Schema for 200 OK response")

class OpenAPIArgs(BaseModel):
    title: str = Field("Autocraft API", description="API title")
    version: str = Field("0.1.0", description="API version")
    endpoints: List[Endpoint] = Field(default_factory=list, description="List of endpoints")
    base_dir: str = Field(".", description="Repo root")
    file: str = Field("openapi.yaml", description="Output file relative to repo root")

def _jsonschema_to_yaml(schema: Dict[str, Any], indent: int = 0) -> str:
    # Simple, minimal YAML conversion for typical JSON Schema structures.
    spaces = "  " * indent
    lines: List[str] = []
    for k, v in schema.items():
        if isinstance(v, dict):
            lines.append(f"{spaces}{k}:")
            lines.append(_jsonschema_to_yaml(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{spaces}{k}:")
            for item in v:
                if isinstance(item, (dict, list)):
                    lines.append(f"{spaces}-")
                    lines.append(_jsonschema_to_yaml(item if isinstance(item, dict) else {"item": item}, indent + 1))
                else:
                    lines.append(f"{spaces}- {item}")
        else:
            lines.append(f"{spaces}{k}: {json.dumps(v)}")
    return "\n".join(lines)

class OpenAPISchemaTool(BaseTool):
    name: str = "OpenAPISchemaTool"
    description: str = "Generates a minimal OpenAPI 3.0 YAML file from a list of endpoints with JSON Schemas."
    #args_schema: ClassVar[type[BaseModel]] = OpenAPIArgs

    def _run(self, title: str = "Autocraft API", version: str = "0.1.0", endpoints: Optional[List[Dict[str, Any]]] = None, base_dir: str = ".", file: str = "openapi.yaml") -> str:
        paths: Dict[str, Dict[str, Any]] = {}
        for ep in (endpoints or []):
            method = ep["method"].lower()
            path = ep["path"]
            if path not in paths:
                paths[path] = {}
            op_block: Dict[str, Any] = {}
            if ep.get("summary"):
                op_block["summary"] = ep["summary"]
            if ep.get("operationId"):
                op_block["operationId"] = ep["operationId"]
            if ep.get("requestSchema"):
                op_block["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": ep["requestSchema"]
                        }
                    }
                }
            if ep.get("responseSchema"):
                op_block.setdefault("responses", {})["200"] = {
                    "description": "OK",
                    "content": {
                        "application/json": {
                            "schema": ep["responseSchema"]
                        }
                    }
                }
            paths[path][method] = op_block or {"responses": {"200": {"description": "OK"}}}

        # Emit YAML by hand (sufficient for small files)
        yaml_lines = [
            "openapi: 3.0.3",
            "info:",
            f"  title: {title}",
            f"  version: {version}",
            "paths:"
        ]
        for pth, methods in paths.items():
            yaml_lines.append(f"  {pth}:")
            for m, spec in methods.items():
                yaml_lines.append(f"    {m}:")
                if "summary" in spec:
                    yaml_lines.append(f"      summary: {spec['summary']}")
                if "operationId" in spec:
                    yaml_lines.append(f"      operationId: {spec['operationId']}")
                if "requestBody" in spec:
                    yaml_lines.append("      requestBody:")
                    yaml_lines.append("        required: true")
                    yaml_lines.append("        content:")
                    yaml_lines.append("          application/json:")
                    yaml_lines.append("            schema:")
                    yaml_lines.append(_jsonschema_to_yaml(spec["requestBody"]["content"]["application/json"]["schema"], indent=6))
                yaml_lines.append("      responses:")
                if "responses" in spec and "200" in spec["responses"]:
                    yaml_lines.append("        '200':")
                    yaml_lines.append("          description: OK")
                    if "content" in spec["responses"]["200"]:
                        yaml_lines.append("          content:")
                        yaml_lines.append("            application/json:")
                        yaml_lines.append("              schema:")
                        yaml_lines.append(_jsonschema_to_yaml(spec["responses"]["200"]["content"]["application/json"]["schema"], indent=6))
                else:
                    yaml_lines.append("        '200':")
                    yaml_lines.append("          description: OK")

        content = "\n".join(yaml_lines) + "\n"
        return _write_file(Path(base_dir) / file, content, overwrite=True)


# -----------------------------
# FakerTool
# -----------------------------

class FakerArgs(BaseModel):
    base_package: str
    class_name: str = "FakeDataExamples"
    base_dir: str = "."
    examples: int = Field(5, description="Number of fake rows to print in example")


FAKER_BODY_TMPL = _read_template("FAKER_BODY_TMPL.j2")

class FakerTool(BaseTool):
    name: str = "FakerTool"
    description: str = "Generates a simple Java class that prints a few lines of fake data using JavaFaker."
    #args_schema: ClassVar[type[BaseModel]] = FakerArgs

    def _run(self, base_package: str, class_name: str = "FakeDataExamples", base_dir: str = ".", examples: int = 5) -> str:
        body = FAKER_BODY_TMPL.replace("%N%", str(examples))
        return JavaCodegenTool()._run(
            base_package=base_package,
            class_name=class_name,
            src_type="main",
            body=body,
            imports=[
                "com.github.javafaker.Faker"
            ],
            javadoc="Auto-generated fake data example using JavaFaker.",
            base_dir=base_dir,
        )

# --- Kafka messaging scaffold (no templates) ---------------------------------
class KafkaMessagingScaffoldTool(BaseTool):
    name: str = "KafkaMessagingScaffoldTool"
    description: str = "Generates Kafka config, producer, consumer, and unit tests without Jinja templates."

    def _run(
        self,
        base_package: str,
        base_dir: str = ".",
        topic: str = "orders",
        client_id: str = "qa-testkit",
        consumer_group: str = "qa-testkit-group",
        acks: str = "all",
        auto_offset_reset: str = "earliest",
        bootstrap_servers: str = "localhost:9092",
    ) -> str:
        created = []

        # KafkaConfig.java
        kafka_config_body = f"""public final class KafkaConfig {{
            private KafkaConfig() {{}}

            public static java.util.Properties producerProps() {{
                java.util.Properties p = new java.util.Properties();
                p.put("bootstrap.servers", "{bootstrap_servers}");
                p.put("client.id", "{client_id}-producer");
                p.put("acks", "{acks}");
                p.put("key.serializer", "org.apache.kafka.common.serialization.StringSerializer");
                p.put("value.serializer", "org.apache.kafka.common.serialization.StringSerializer");
                return p;
            }}

            public static java.util.Properties consumerProps() {{
                java.util.Properties p = new java.util.Properties();
                p.put("bootstrap.servers", "{bootstrap_servers}");
                p.put("group.id", "{consumer_group}");
                p.put("auto.offset.reset", "{auto_offset_reset}");
                p.put("key.deserializer", "org.apache.kafka.common.serialization.StringDeserializer");
                p.put("value.deserializer", "org.apache.kafka.common.serialization.StringDeserializer");
                return p;
            }}
            }}"""
        created.append(JavaCodegenTool()._run(
            base_package=base_package,
            class_name="KafkaConfig",
            src_type="main",
            body=kafka_config_body,
            imports=["java.util.Properties",
                     "org.apache.kafka.common.serialization.*"],
            javadoc="Auto-generated Kafka configuration.",
            base_dir=base_dir,
        ))

        # KafkaProducerClient.java
        producer_body = f"""private final org.apache.kafka.clients.producer.KafkaProducer<String, String> producer;
            private final String topic;

            public KafkaProducerClient(java.util.Properties props, String topic) {{
                this.producer = new org.apache.kafka.clients.producer.KafkaProducer<>(props);
                this.topic = topic;
            }}

            public void send(String key, String jsonValue) {{
                producer.send(new org.apache.kafka.clients.producer.ProducerRecord<>(topic, key, jsonValue));
                producer.flush();
            }}

            @Override public void close() {{ producer.close(); }}"""
        created.append(JavaCodegenTool()._run(
                base_package=base_package + ".messaging.kafka",
                class_name="KafkaProducerClient",
                src_type="main",
                body=producer_body,
                imports=[
                    "java.util.Properties",
                    "org.apache.kafka.clients.producer.KafkaProducer",
                    "org.apache.kafka.clients.producer.ProducerRecord",
                ],
                javadoc="Auto-generated Kafka producer client.",
                base_dir=base_dir,
            ))

            # KafkaConsumerClient.java
        consumer_body = f"""private final org.apache.kafka.clients.consumer.KafkaConsumer<String, String> consumer;

            public KafkaConsumerClient(java.util.Properties props, String topic) {{
                this.consumer = new org.apache.kafka.clients.consumer.KafkaConsumer<>(props);
                this.consumer.subscribe(java.util.Collections.singletonList(topic));
            }}

            public org.apache.kafka.clients.consumer.ConsumerRecords<String, String> pollOnce(java.time.Duration timeout) {{
                return consumer.poll(timeout);
            }}

            @Override public void close() {{ consumer.close(); }}"""
        created.append(JavaCodegenTool()._run(
                base_package=base_package + ".messaging.kafka",
                class_name="KafkaConsumerClient",
                src_type="main",
                body=consumer_body,
                imports=[
                    "java.util.Collections",
                    "java.time.Duration",
                    "org.apache.kafka.clients.consumer.KafkaConsumer",
                    "org.apache.kafka.clients.consumer.ConsumerRecords",
                ],
                javadoc="Auto-generated Kafka consumer client.",
                base_dir=base_dir,
            ))

            # KafkaProducerTest.java (MockProducer)
        prod_test_body = f"""@org.junit.jupiter.api.Test
            void mock_producer_sends_records() {{
                org.apache.kafka.clients.producer.MockProducer<String, String> producer =
                    new org.apache.kafka.clients.producer.MockProducer<>(true, null, null);
                producer.send(new org.apache.kafka.clients.producer.ProducerRecord<>("{topic}", "key", "value"));
                producer.completeNext();
                org.assertj.core.api.Assertions.assertThat(producer.history()).hasSize(1);
            }}"""
        created.append(JavaCodegenTool()._run(
            base_package=base_package + ".messaging.kafka",
            class_name="KafkaProducerTest",
            src_type="test",
            body=prod_test_body,
            imports=[
                "org.junit.jupiter.api.*",
                "org.assertj.core.api.Assertions",
                "org.apache.kafka.clients.producer.*",
            ],
            javadoc="Auto-generated unit test for Kafka producer using MockProducer.",
            base_dir=base_dir,
        ))

        # KafkaConsumerTest.java (MockConsumer)
        cons_test_body = f"""@org.junit.jupiter.api.Test
            void mock_consumer_reads_records() {{
                org.apache.kafka.clients.consumer.MockConsumer<String, String> consumer =
                    new org.apache.kafka.clients.consumer.MockConsumer<>(org.apache.kafka.clients.consumer.OffsetResetStrategy.EARLIEST);
                java.util.Map<org.apache.kafka.common.TopicPartition, Long> startOffsets = new java.util.HashMap<>();
                org.apache.kafka.common.TopicPartition tp = new org.apache.kafka.common.TopicPartition("{topic}", 0);
                startOffsets.put(tp, 0L);
                consumer.assign(java.util.Collections.singletonList(tp));
                consumer.updateBeginningOffsets(startOffsets);
                consumer.addRecord(new org.apache.kafka.clients.consumer.ConsumerRecord<>("{topic}", 0, 0L, "k", "v"));
                org.apache.kafka.clients.consumer.ConsumerRecords<String, String> polled = consumer.poll(java.time.Duration.ofMillis(10));
                org.assertj.core.api.Assertions.assertThat(polled.count()).isEqualTo(1);
            }}"""
        created.append(JavaCodegenTool()._run(
            base_package=base_package + ".messaging.kafka",
            class_name="KafkaConsumerTest",
            src_type="test",
            body=cons_test_body,
            imports=[
                "java.util.*",
                "java.time.Duration",
                "org.junit.jupiter.api.*",
                "org.assertj.core.api.Assertions",
                "org.apache.kafka.common.TopicPartition",
                "org.apache.kafka.clients.consumer.*",
            ],
            javadoc="Auto-generated unit test for Kafka consumer using MockConsumer.",
            base_dir=base_dir,
        ))

        return "\n".join(created)


# --- EMS (JMS / TIBCO EMS) scaffold (no templates) ---------------------------
class EmsMessagingScaffoldTool(BaseTool):
    name: str = "EmsMessagingScaffoldTool"
    description: str = "Generates JMS/EMS config, producer, consumer, and Mockito-based unit tests without templates."

    def _run(
        self,
        base_package: str,
        base_dir: str = ".",
        queue_name: str = "demo.queue",
        jndi_initial_ctx: str = "com.tibco.tibjms.naming.TibjmsInitialContextFactory",
        provider_url: str = "tibjmsnaming://localhost:7222",
        factory_jndi: str = "QueueConnectionFactory",
    ) -> str:
        created = []

        # EmsConfig.java (JNDI + direct example)
        config_body = f"""public final class EmsConfig {{
            private EmsConfig() {{}}

            public static javax.jms.ConnectionFactory jndiConnectionFactory(String providerUrl, String factoryJndi) throws Exception {{
                java.util.Hashtable<String,String> env = new java.util.Hashtable<>();
                env.put(javax.naming.Context.INITIAL_CONTEXT_FACTORY, "{jndi_initial_ctx}");
                env.put(javax.naming.Context.PROVIDER_URL, providerUrl);
                javax.naming.Context ctx = new javax.naming.InitialContext(env);
                return (javax.jms.ConnectionFactory) ctx.lookup(factoryJndi);
            }}

            public static javax.jms.ConnectionFactory directConnectionFactory(String serverUrl) throws Exception {{
                return (javax.jms.ConnectionFactory) Class
                    .forName("com.tibco.tibjms.TibjmsConnectionFactory")
                    .getConstructor(String.class)
                    .newInstance(serverUrl);
            }}
            }}"""
        created.append(JavaCodegenTool()._run(
            base_package=base_package + ".messaging.ems",
            class_name="EmsConfig",
            src_type="main",
            body=config_body,
            imports=["javax.jms.*", "javax.naming.*", "java.util.Hashtable"],
            javadoc="Auto-generated EMS/JMS configuration helpers (JNDI/direct).",
            base_dir=base_dir,
        ))

        # EmsProducer.java
        producer_body = f"""private final javax.jms.Connection connection;
            private final javax.jms.Session session;
            private final javax.jms.MessageProducer producer;

            public EmsProducer(javax.jms.ConnectionFactory cf, String queueName, String user, String pass) throws javax.jms.JMSException {{
                this.connection = (user != null) ? cf.createConnection(user, pass) : cf.createConnection();
                this.connection.start();
                this.session = connection.createSession(false, javax.jms.Session.AUTO_ACKNOWLEDGE);
                javax.jms.Queue q = session.createQueue(queueName);
                this.producer = session.createProducer(q);
            }}

            public void sendText(String text) throws javax.jms.JMSException {{
                javax.jms.TextMessage msg = session.createTextMessage(text);
                producer.send(msg);
            }}

            @Override public void close() throws javax.jms.JMSException {{
                try {{ producer.close(); }} finally {{
                    try {{ session.close(); }} finally {{ connection.close(); }}
                }}
            }}"""
        created.append(JavaCodegenTool()._run(
            base_package=base_package + ".messaging.ems",
            class_name="EmsProducer",
            src_type="main",
            body=producer_body,
            imports=["javax.jms.*"],
            javadoc="Auto-generated EMS producer wrapper.",
            base_dir=base_dir,
        ))

        # EmsConsumer.java
        consumer_body = f"""private final javax.jms.Connection connection;
            private final javax.jms.Session session;
            private final javax.jms.MessageConsumer consumer;

            public EmsConsumer(javax.jms.ConnectionFactory cf, String queueName, String user, String pass) throws javax.jms.JMSException {{
                this.connection = (user != null) ? cf.createConnection(user, pass) : cf.createConnection();
                this.connection.start();
                this.session = connection.createSession(false, javax.jms.Session.AUTO_ACKNOWLEDGE);
                javax.jms.Queue q = session.createQueue(queueName);
                this.consumer = session.createConsumer(q);
            }}

            public String receiveText(long timeoutMillis) throws javax.jms.JMSException {{
                javax.jms.Message m = consumer.receive(timeoutMillis);
                if (m == null) return null;
                if (m instanceof javax.jms.TextMessage) return ((javax.jms.TextMessage)m).getText();
                throw new javax.jms.MessageFormatException("Expected TextMessage");
            }}

            @Override public void close() throws javax.jms.JMSException {{
                try {{ consumer.close(); }} finally {{
                    try {{ session.close(); }} finally {{ connection.close(); }}
                }}
            }}"""
        created.append(JavaCodegenTool()._run(
            base_package=base_package + ".messaging.ems",
            class_name="EmsConsumer",
            src_type="main",
            body=consumer_body,
            imports=["javax.jms.*"],
            javadoc="Auto-generated EMS consumer wrapper.",
            base_dir=base_dir,
        ))

        # EmsProducerTest.java (Mockito unit test)
        producer_test_body = _read_template("PRODUCER_TEST_BODY.j2")
        created.append(JavaCodegenTool()._run(
            base_package=base_package + ".messaging.ems",
            class_name="EmsProducerTest",
            src_type="test",
            body=producer_test_body,
            imports=[
                "org.junit.jupiter.api.*",
                "org.mockito.Mockito",
                "javax.jms.*",
            ],
            javadoc="Auto-generated Mockito unit test for EMS producer.",
            base_dir=base_dir,
        ))

        # EmsConsumerTest.java (Mockito unit test)
        consumer_test_body = _read_template("CONSUMER_TEST_BODY.j2")
        created.append(JavaCodegenTool()._run(
            base_package=base_package + ".messaging.ems",
            class_name="EmsConsumerTest",
            src_type="test",
            body=consumer_test_body,
            imports=[
                "org.junit.jupiter.api.*",
                "org.assertj.core.api.Assertions",
                "org.mockito.Mockito",
                "javax.jms.*",
            ],
            javadoc="Auto-generated Mockito unit test for EMS consumer.",
            base_dir=base_dir,
        ))

        return "\n".join(created)



# -----------------------------
# Convenience: tool registry
# -----------------------------

TOOLS_REGISTRY = {
    "FileWriterTool": FileWriterTool,
    "RepoScaffolderTool": RepoScaffolderTool,
    "PomXmlTool": PomXmlTool,
    "JavaCodegenTool": JavaCodegenTool,
    "ReadmeWriterTool": ReadmeWriterTool,
    "H2RunnerTool": H2RunnerTool,
    "JDBCExecutorTool": JDBCExecutorTool,
    "MongoEmbedTool": MongoEmbedTool,
    "TestcontainersTool": TestcontainersTool,
    "KafkaMockTool": KafkaMockTool,
    "OpenAPISchemaTool": OpenAPISchemaTool,
    "FakerTool": FakerTool,
    "KafkaMessagingScaffoldTool": KafkaMessagingScaffoldTool,
    "EmsMessagingScaffoldTool": EmsMessagingScaffoldTool,
}


def get_tool_by_name(name: str) -> BaseTool:
    """Factory to instantiate a tool by its class name."""
    cls = TOOLS_REGISTRY.get(name)
    if not cls:
        raise KeyError(f"Unknown tool '{name}'. Known tools: {list(TOOLS_REGISTRY)}")
    return cls()