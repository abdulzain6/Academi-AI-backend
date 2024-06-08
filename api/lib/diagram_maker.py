import re
import vl_convert as vlc
from .mermaid_maker import MermaidClient
from .uml_diagram_maker import PlantUML
from graphviz import Source
from langchain_core.tools import tool
from langchain.chat_models.base import BaseChatModel
from retrying import retry

class DiagramMaker:
    def __init__(self, mermaid_client: MermaidClient, model: BaseChatModel, generator: PlantUML) -> None:
        self.mermaid_client = mermaid_client
        self.llm = model
        self.uml_generator = generator

    def extract_code(self, markdown_text: str) -> str:
        """
        Extracts content from code blocks in markdown.
        Supports blocks that use triple backticks with optional language identifiers.
        """
        # Enhanced regex to handle nested content or special characters
        code_blocks = re.findall(r'```[\w\s]*\n(.*?)```', markdown_text, re.DOTALL)
        if code_blocks:
            # Join multiple code blocks with a newline
            return '\n\n'.join(code_blocks).strip()
        return markdown_text  # Return original if no code blocks are found
            
    @retry(stop_max_attempt_number=3)
    def make_diagram(self, prompt: str, instructions: str = "") -> bytes:
        @tool
        def make_mermaid_diagram(mermaid_code: str) -> bytes:
            "Used to make Diagrams using Mermaid.js Code"
            mermaid_code = self.extract_code(mermaid_code)
            return self.mermaid_client.get_diagram_image(diagram_code=mermaid_code, image_type="png")

        @tool
        def make_vegalite_graph(vegalite_spec: str) -> bytes:
            "Used to make diagrams using vegalite"
            vegalite_spec = self.extract_code(vegalite_spec)
            return vlc.vegalite_to_png(vl_spec=vegalite_spec, scale=2)
        
        @tool
        def make_graphviz_graph(dot_code: str) -> bytes:
            "Used to make diagrams using graphviz"
            dot_code = self.extract_code(dot_code)
            dot = Source(dot_code)
            return dot.pipe(format='png')
        
        @tool
        def make_uml_diagram(plantuml_code: str) -> bytes:
            "Used to make diagrams using graphviz"
            plantuml_code = self.extract_code(plantuml_code)
            data = self.uml_generator.processes(plantuml_code)
            return data
        
        
        tools = [make_graphviz_graph, make_vegalite_graph, make_mermaid_diagram, make_uml_diagram]
        tool_map = {tool.name: tool for tool in tools}
        llm_with_tools = self.llm.bind_tools(tools, tool_choice="required")
        instructions = f"\nFollow the following instructions: {instructions}" if instructions else  ""
        output =  llm_with_tools.invoke(prompt + instructions)
        print(output)
        tool_call = output.tool_calls[0]
        output = tool_map[tool_call["name"]].invoke(tool_call["args"])
        return output
        

    
if __name__ == '__main__':
    from langchain_openai.chat_models import ChatOpenAI
    diagram_maker = DiagramMaker(MermaidClient("http://localhost:9001"), ChatOpenAI(temperature=0), PlantUML(url="http://localhost:9080/img/"))
    output = diagram_maker.make_diagram("Bar graph")
    with open("output.png", "wb") as fp:
        fp.write(output)
    print(output)