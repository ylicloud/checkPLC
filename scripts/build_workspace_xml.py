"""Generate TIA VCI Openness XML into workspace/ for IO test blocks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "workspace"

NS_IF = "http://www.siemens.com/automation/Openness/SW/Interface/v5"
NS_ST = "http://www.siemens.com/automation/Openness/SW/NetworkSource/StructuredText/v4"
NS_FLG = "http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v5"


def ml(text: str, uid: int, composition: str = "Comment") -> str:
    return f"""      <MultilingualText ID="{uid}" CompositionName="{composition}">
        <ObjectList>
          <MultilingualTextItem ID="{uid + 1}" CompositionName="Items">
            <AttributeList>
              <Culture>zh-CN</Culture>
              <Text>{text}</Text>
            </AttributeList>
          </MultilingualTextItem>
        </ObjectList>
      </MultilingualText>"""


def wrap(body: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Document>
  <Engineering version="V20" />
{body}
</Document>
"""


def udt_dig() -> str:
    return wrap(
        f"""  <SW.Types.PlcStruct ID="0">
    <AttributeList>
      <Interface><Sections xmlns="{NS_IF}">
  <Section Name="None">
    <Member Name="Enable" Datatype="Bool" />
    <Member Name="StartAddr" Datatype="UInt" />
    <Member Name="ChannelCount" Datatype="USInt" />
    <Member Name="Reserved" Datatype="USInt" />
  </Section>
</Sections></Interface>
      <Name>UDT_DigSlot</Name>
      <Namespace />
    </AttributeList>
    <ObjectList>
{ml("DI/DQ module slot", 1)}
    </ObjectList>
  </SW.Types.PlcStruct>"""
    )


def udt_ana() -> str:
    return wrap(
        f"""  <SW.Types.PlcStruct ID="0">
    <AttributeList>
      <Interface><Sections xmlns="{NS_IF}">
  <Section Name="None">
    <Member Name="Enable" Datatype="Bool" />
    <Member Name="StartAddr" Datatype="UInt" />
    <Member Name="ChannelCount" Datatype="USInt" />
    <Member Name="Reserved" Datatype="USInt" />
    <Member Name="RawFull" Datatype="Int">
      <StartValue>27648</StartValue>
    </Member>
    <Member Name="EngMax_mA" Datatype="Real">
      <StartValue>20.0</StartValue>
    </Member>
    <Member Name="EngMin_mA" Datatype="Real">
      <StartValue>4.0</StartValue>
    </Member>
  </Section>
</Sections></Interface>
      <Name>UDT_AnaSlot</Name>
      <Namespace />
    </AttributeList>
    <ObjectList>
{ml("AI/AQ module slot 4-20mA", 1)}
    </ObjectList>
  </SW.Types.PlcStruct>"""
    )


def db_config() -> str:
    return wrap(
        f"""  <SW.Blocks.GlobalDB ID="0">
    <AttributeList>
      <AutoNumber>false</AutoNumber>
      <HeaderVersion>0.1</HeaderVersion>
      <Interface><Sections xmlns="{NS_IF}">
  <Section Name="Static">
    <Member Name="DI" Datatype="Array[1..20] of &quot;UDT_DigSlot&quot;" />
    <Member Name="DQ" Datatype="Array[1..20] of &quot;UDT_DigSlot&quot;" />
    <Member Name="AI" Datatype="Array[1..20] of &quot;UDT_AnaSlot&quot;" />
    <Member Name="AQ" Datatype="Array[1..20] of &quot;UDT_AnaSlot&quot;" />
  </Section>
</Sections></Interface>
      <IsOnlyStoredInLoadMemory>false</IsOnlyStoredInLoadMemory>
      <IsWriteProtectedInAS>false</IsWriteProtectedInAS>
      <MemoryLayout>Standard</MemoryLayout>
      <Name>DB_IO_Config</Name>
      <Namespace />
      <Number>10</Number>
      <ProgrammingLanguage>DB</ProgrammingLanguage>
    </AttributeList>
    <ObjectList>
{ml("IO test config DB10 non-optimized", 1)}
{ml("DB_IO_Config", 3, "Title")}
    </ObjectList>
  </SW.Blocks.GlobalDB>"""
    )


def db_runtime() -> str:
    return wrap(
        f"""  <SW.Blocks.GlobalDB ID="0">
    <AttributeList>
      <AutoNumber>false</AutoNumber>
      <HeaderVersion>0.1</HeaderVersion>
      <Interface><Sections xmlns="{NS_IF}">
  <Section Name="Static">
    <Member Name="DQ_Force" Datatype="Array[1..20] of DWORD" />
    <Member Name="AQ_mA" Datatype="Array[1..160] of Real" />
    <Member Name="Heartbeat" Datatype="UInt" />
  </Section>
</Sections></Interface>
      <IsOnlyStoredInLoadMemory>false</IsOnlyStoredInLoadMemory>
      <IsWriteProtectedInAS>false</IsWriteProtectedInAS>
      <MemoryLayout>Standard</MemoryLayout>
      <Name>DB_IO_Runtime</Name>
      <Namespace />
      <Number>11</Number>
      <ProgrammingLanguage>DB</ProgrammingLanguage>
    </AttributeList>
    <ObjectList>
{ml("IO test runtime DB11 non-optimized", 1)}
{ml("DB_IO_Runtime", 3, "Title")}
    </ObjectList>
  </SW.Blocks.GlobalDB>"""
    )


def scl_to_structured_text(body: str) -> str:
    """Emit StructuredText as Token Text lines (Openness SCL_v2 style, simplified)."""
    lines: list[str] = []
    uid = 100
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            lines.append(f'              <NewLine Num="{uid}" />')
            uid += 1
            continue
        # escape XML
        text = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        lines.append(f'              <Token Text="{text}" UId="{uid}" />')
        uid += 1
        lines.append(f'              <NewLine Num="{uid}" />')
        uid += 1
    inner = "\n".join(lines)
    return f"""            <StructuredText xmlns="{NS_ST}">
{inner}
            </StructuredText>"""


def fc_apply() -> str:
    # Body only (BEGIN.. before END_FUNCTION) — temps go in Interface
    body = r"""
"DB_IO_Runtime".Heartbeat := "DB_IO_Runtime".Heartbeat + 1;

FOR slot := 1 TO 20 DO
  IF "DB_IO_Config".DQ[slot].Enable THEN
    startAddr := "DB_IO_Config".DQ[slot].StartAddr;
    chCount := USINT_TO_INT("DB_IO_Config".DQ[slot].ChannelCount);
    IF chCount > 32 THEN
      chCount := 32;
    END_IF;
    forceDword := "DB_IO_Runtime".DQ_Force[slot];
    FOR ch := 0 TO chCount - 1 DO
      bitVal := (forceDword AND SHL(IN := DWORD#1, N := ch)) <> DWORD#0;
      byteIndex := UINT_TO_INT(startAddr) + (ch / 8);
      bitIndex := ch MOD 8;
      qByte := PEEK(area := 16#82, dbNumber := 0, byteOffset := byteIndex);
      IF bitVal THEN
        qByte := qByte OR SHL(IN := BYTE#1, N := bitIndex);
      ELSE
        qByte := qByte AND (NOT SHL(IN := BYTE#1, N := bitIndex));
      END_IF;
      POKE(area := 16#82, dbNumber := 0, byteOffset := byteIndex, value := qByte);
    END_FOR;
  END_IF;
END_FOR;

globalCh := 0;
FOR slot := 1 TO 20 DO
  IF "DB_IO_Config".AQ[slot].Enable THEN
    startAddr := "DB_IO_Config".AQ[slot].StartAddr;
    chCount := USINT_TO_INT("DB_IO_Config".AQ[slot].ChannelCount);
    rawFull := "DB_IO_Config".AQ[slot].RawFull;
    engMax := "DB_IO_Config".AQ[slot].EngMax_mA;
    engMin := "DB_IO_Config".AQ[slot].EngMin_mA;
    IF engMax <= engMin THEN
      engMax := 20.0;
      engMin := 4.0;
    END_IF;
    IF rawFull = 0 THEN
      rawFull := 27648;
    END_IF;
    FOR ch := 0 TO chCount - 1 DO
      globalCh := globalCh + 1;
      IF globalCh > 160 THEN
        EXIT;
      END_IF;
      mA := INT_TO_REAL(4 + ((globalCh - 1) MOD 8)); // 4~11 mA 循环
      "DB_IO_Runtime".AQ_mA[globalCh] := mA;
      raw := REAL_TO_INT((mA - engMin) / (engMax - engMin) * INT_TO_REAL(rawFull));
      IF raw > rawFull THEN
        raw := rawFull;
      END_IF;
      IF raw < 0 THEN
        raw := 0;
      END_IF;
      outWord := INT_TO_WORD(raw);
      POKE_W(area := 16#82, dbNumber := 0, byteOffset := UINT_TO_INT(startAddr) + ch * 2, value := outWord);
    END_FOR;
  END_IF;
END_FOR;
""".strip(
        "\n"
    )

    st = scl_to_structured_text(body)
    return wrap(
        f"""  <SW.Blocks.FC ID="0">
    <AttributeList>
      <AutoNumber>false</AutoNumber>
      <HeaderVersion>0.1</HeaderVersion>
      <Interface><Sections xmlns="{NS_IF}">
  <Section Name="Input" />
  <Section Name="Output" />
  <Section Name="InOut" />
  <Section Name="Temp">
    <Member Name="slot" Datatype="Int" />
    <Member Name="ch" Datatype="Int" />
    <Member Name="globalCh" Datatype="Int" />
    <Member Name="byteIndex" Datatype="Int" />
    <Member Name="bitIndex" Datatype="Int" />
    <Member Name="forceDword" Datatype="DWORD" />
    <Member Name="bitVal" Datatype="Bool" />
    <Member Name="qByte" Datatype="Byte" />
    <Member Name="startAddr" Datatype="UInt" />
    <Member Name="chCount" Datatype="Int" />
    <Member Name="mA" Datatype="Real" />
    <Member Name="raw" Datatype="Int" />
    <Member Name="rawFull" Datatype="Int" />
    <Member Name="engMax" Datatype="Real" />
    <Member Name="engMin" Datatype="Real" />
    <Member Name="outWord" Datatype="Word" />
  </Section>
  <Section Name="Constant" />
  <Section Name="Return">
    <Member Name="Ret_Val" Datatype="Void" />
  </Section>
</Sections></Interface>
      <MemoryLayout>Optimized</MemoryLayout>
      <Name>FC_IO_Apply</Name>
      <Namespace />
      <Number>100</Number>
      <ProgrammingLanguage>SCL</ProgrammingLanguage>
      <SetENOAutomatically>false</SetENOAutomatically>
    </AttributeList>
    <ObjectList>
{ml("IO apply DQ force and AQ ramp", 1)}
      <SW.Blocks.CompileUnit ID="10" CompositionName="CompileUnits">
        <AttributeList>
          <NetworkSource>
{st}
          </NetworkSource>
          <ProgrammingLanguage>SCL</ProgrammingLanguage>
        </AttributeList>
        <ObjectList>
{ml("", 11)}
{ml("Network 1", 13, "Title")}
        </ObjectList>
      </SW.Blocks.CompileUnit>
{ml("FC_IO_Apply", 20, "Title")}
    </ObjectList>
  </SW.Blocks.FC>"""
    )


def main_ob() -> str:
    # LAD call FC_IO_Apply
    return wrap(
        f"""  <SW.Blocks.OB ID="0">
    <AttributeList>
      <Interface><Sections xmlns="{NS_IF}">
  <Section Name="Input">
    <Member Name="Initial_Call" Datatype="Bool" Informative="true" />
    <Member Name="Remanence" Datatype="Bool" Informative="true" />
  </Section>
  <Section Name="Temp" />
  <Section Name="Constant" />
</Sections></Interface>
      <MemoryLayout>Optimized</MemoryLayout>
      <Name>Main</Name>
      <Namespace />
      <Number>1</Number>
      <ProgrammingLanguage>LAD</ProgrammingLanguage>
      <SecondaryType>ProgramCycle</SecondaryType>
      <SetENOAutomatically>false</SetENOAutomatically>
    </AttributeList>
    <ObjectList>
{ml("", 1)}
      <SW.Blocks.CompileUnit ID="10" CompositionName="CompileUnits">
        <AttributeList>
          <NetworkSource>
            <FlgNet xmlns="{NS_FLG}">
              <Parts>
                <Call UId="21">
                  <CallInfo Name="FC_IO_Apply" BlockType="FC" />
                </Call>
              </Parts>
              <Wires>
                <Wire UId="22">
                  <Powerrail />
                  <NameCon UId="21" Name="en" />
                </Wire>
              </Wires>
            </FlgNet>
          </NetworkSource>
          <ProgrammingLanguage>LAD</ProgrammingLanguage>
        </AttributeList>
        <ObjectList>
{ml("Call FC_IO_Apply", 11)}
{ml("IO Apply", 13, "Title")}
        </ObjectList>
      </SW.Blocks.CompileUnit>
{ml("Main Program Sweep (Cycle)", 20, "Title")}
    </ObjectList>
  </SW.Blocks.OB>"""
    )


def readme() -> str:
    return """# Workspace 导入说明

## 推荐导入顺序

| 顺序 | 文件 | 拖到 |
|------|------|------|
| 1 | `UDT_DigSlot.xml` | PLC 数据类型 |
| 2 | `UDT_AnaSlot.xml` | PLC 数据类型 |
| 3 | `DB_IO_Config.xml` | 程序块 |
| 4 | `DB_IO_Runtime.xml` | 程序块 |
| 5 | **`FC_IO_Apply.scl`** | 程序块（只用 scl） |
| 6 | `Main.xml` | OB1 |

然后编译并下载。

## 注意

FC 请用 **`FC_IO_Apply.scl`**。手写 Openness SCL XML 会报 `token is not supported`，已不再提供 xml。
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # FC 只用 .scl（Openness SCL Token XML 手写易失败，已验证 .scl 可导入）
    files = {
        "UDT_DigSlot.xml": udt_dig(),
        "UDT_AnaSlot.xml": udt_ana(),
        "DB_IO_Config.xml": db_config(),
        "DB_IO_Runtime.xml": db_runtime(),
        "Main.xml": main_ob(),
        "README_IMPORT.md": readme(),
    }
    for name, content in files.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print("wrote", path.relative_to(ROOT))
    # ensure scl present
    src = ROOT / "plc" / "scl" / "FC_IO_Apply.scl"
    dst = OUT / "FC_IO_Apply.scl"
    if src.exists():
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print("wrote", dst.relative_to(ROOT))
    # remove obsolete broken xml if present
    old = OUT / "FC_IO_Apply.xml"
    if old.exists():
        old.unlink()
        print("removed", old.relative_to(ROOT))


if __name__ == "__main__":
    main()
