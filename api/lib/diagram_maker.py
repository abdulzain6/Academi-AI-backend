from io import BytesIO
from .mermaid_maker import MermaidClient
from .uml_diagram_maker import PlantUML
from graphviz import Source
from langchain_core.tools import tool
from langchain.chat_models.base import BaseChatModel
from retrying import retry
from PIL import Image
import requests
import re
import replicate
import vl_convert as vlc
import cairosvg
import logging

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
    
    def svg_to_png(self, svg_content: bytes, width: int, height: int) -> bytes:
        """
        Convert SVG to PNG with specified dimensions.
        
        :param svg_content: The SVG content as a string
        :param width: Desired width of the output PNG
        :param height: Desired height of the output PNG
        :return: PNG image as bytes
        """
        # Create a BytesIO object to hold the PNG data
        png_io = BytesIO()
        
        # Convert SVG to PNG
        cairosvg.svg2png(bytestring=svg_content,
                        write_to=png_io,
                        output_width=width,
                        output_height=height)
        
        # Get the PNG data as bytes
        png_data = png_io.getvalue()
        png_io.close()
        
        return png_data
            
    @retry(stop_max_attempt_number=3)
    def make_diagram(self, prompt: str, instructions: str = "") -> bytes:
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
        
    #    @tool
    #    def make_uml_diagram(plantuml_code: str) -> bytes:
    #        "Used to make diagrams using plantuml"
    #        plantuml_code = self.extract_code(plantuml_code)
    #        data = self.uml_generator.processes(plantuml_code)
    #        return data
        
        
        tools = [make_graphviz_graph, make_vegalite_graph]
        tool_map = {tool.name: tool for tool in tools}
        llm_with_tools = self.llm.bind_tools(tools, tool_choice="required")
        instructions = f"\nFollow the following instructions: {instructions}" if instructions else  ""
        output =  llm_with_tools.invoke(prompt + instructions)
        tool_call = output.tool_calls[0]
        output = tool_map[tool_call["name"]].invoke(tool_call["args"])
        return output
        
    @retry(stop_max_attempt_number=3)
    def make_diagram_with_dimensions(self, prompt: str, width: int, height: int) -> bytes:
        @tool
        def make_vegalite_graph(vegalite_spec: str) -> bytes:
            "Used to make diagrams using vegalite"
            vegalite_spec = self.extract_code(vegalite_spec)
            return self.svg_to_png(
                vlc.vegalite_to_svg(vl_spec=vegalite_spec, scale=2),
                width,
                height
            )
                
        @tool
        def make_graphviz_graph(dot_code: str) -> bytes:
            "Used to make diagrams using graphviz"
            dot_code = self.extract_code(dot_code)
            dot = Source(dot_code)
            return self.svg_to_png(
                dot.pipe(format='svg'),
                width,
                height
            )
        
        @tool
        def generate_image(prompt: str, width: int, height: int) -> bytes:
            """
            Generates image based on prompt using image model, then resizes intelligently and returns as PNG bytes.
            """
            input = {
                "prompt": prompt,
                "aspect_ratio": "16:9",  # Default aspect ratio for generation
                "num_outputs": 1
            }

            # Generate image URL
            image_url = replicate.run(
                "black-forest-labs/flux-schnell",
                input=input
            )[0]

            # Download the image
            response = requests.get(image_url)
            if response.status_code != 200:
                raise Exception("Failed to download the generated image")

            # Open the image with Pillow
            img = Image.open(BytesIO(response.content))

            # Calculate aspect ratios
            target_ratio = width / height
            img_ratio = img.width / img.height

            if target_ratio > img_ratio:
                # Target is wider, resize based on width
                new_width = width
                new_height = int(width / img_ratio)
            else:
                # Target is taller, resize based on height
                new_height = height
                new_width = int(height * img_ratio)

            # Resize the image
            img_resized = img.resize((new_width, new_height), Image.LANCZOS)

            # Create a new image with the target size and paste the resized image
            new_img = Image.new('RGB', (width, height), (255, 255, 255))  # White background
            paste_x = (width - new_width) // 2
            paste_y = (height - new_height) // 2
            new_img.paste(img_resized, (paste_x, paste_y))

            # Convert to PNG and get bytes
            img_byte_arr = BytesIO()
            new_img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

            return img_byte_arr
            
        
        logging.info(f"Making diagram for '{prompt}' Width: {width}, Height : {height}")
        tools = [make_graphviz_graph, make_vegalite_graph, generate_image]
        tool_map = {tool.name: tool for tool in tools}
        llm_with_tools = self.llm.bind_tools(tools, tool_choice="required")
        output =  llm_with_tools.invoke(prompt)
        tool_call = output.tool_calls[0]
        output = tool_map[tool_call["name"]].invoke(tool_call["args"])
        return output

    
if __name__ == '__main__':
    from langchain_openai.chat_models import ChatOpenAI
    diagram_maker = DiagramMaker(MermaidClient("http://localhost:9001"), ChatOpenAI(temperature=0), PlantUML(url="http://localhost:9080/img/"))
    output = diagram_maker.make_diagram_with_dimensions("Cat eating frog, ben10 in background", 1000,1000)
    with open("output.png", "wb") as fp:
        fp.write(output)
    print(output)