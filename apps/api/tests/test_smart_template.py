# import pytest (removed)
from app.services.template_service import template_service
from app.schemas.smart_template import SmartTemplate, TemplateBlock, BlockType, TemplateRenderInput

def test_assemble_smart_template():
    # 1. Define Template
    blocks = [
        TemplateBlock(id="1", type=BlockType.FIXED, title="Header", content="HEADER"),
        TemplateBlock(id="2", type=BlockType.VARIABLE, title="Client Name", variable_name="client_name"),
        TemplateBlock(id="3", type=BlockType.AI, title="Argumentation", lockable=True, user_can_edit=True),
        TemplateBlock(id="4", type=BlockType.FIXED, title="Footer", content="FOOTER", user_can_edit=False),
    ]
    template = SmartTemplate(id="t1", name="Test", blocks=blocks)

    # 2. Test Input with variables and overrides
    input_data = TemplateRenderInput(
        template_id="t1",
        variables={"client_name": "John Doe"},
        overrides={"3": "AI GENERATED TEXT", "4": "MALICIOUS OVERRIDE"}
    )

    # 3. Assemble
    result = template_service.assemble_smart_template(template, input_data)

    # 4. Verify
    # Expect: HEADER, then John Doe, then AI GENERATED TEXT (override accepted), then FOOTER (override ignored)
    expected = "HEADER\n\nJohn Doe\n\nAI GENERATED TEXT\n\nFOOTER"
    
    # We should normalize newlines just in case but join uses \n\n
    assert result == expected

def test_assemble_smart_template_conditions():
    blocks = [
        TemplateBlock(id="1", type=BlockType.FIXED, title="Always", content="ALWAYS"),
        TemplateBlock(id="2", type=BlockType.FIXED, title="Conditional", content="CONDITIONAL", condition="show_cond"),
    ]
    template = SmartTemplate(id="t2", name="Test Cond", blocks=blocks)
    
    # Case 1: show_cond = False
    input_data = TemplateRenderInput(template_id="t2", variables={"show_cond": False})
    result = template_service.assemble_smart_template(template, input_data)
    assert result == "ALWAYS"
    
    # Case 2: show_cond = True
    input_data2 = TemplateRenderInput(template_id="t2", variables={"show_cond": True})
    result2 = template_service.assemble_smart_template(template, input_data2)
    assert result2 == "ALWAYS\n\nCONDITIONAL"

if __name__ == "__main__":
    try:
        test_assemble_smart_template()
        print("test_assemble_smart_template PASSED")
        test_assemble_smart_template_conditions()
        print("test_assemble_smart_template_conditions PASSED")
    except AssertionError as e:
        import traceback
        traceback.print_exc()
        exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        exit(1)

