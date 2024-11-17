import random, concurrent.futures
from PIL import Image
from langchain.pydantic_v1 import BaseModel
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from .infographic_maker.infographic_maker import InfographicMaker


class Content(BaseModel):
    page_contents_markdown: list[str]

class ImageExplainers:
    def __init__(
        self,
        llm: BaseChatModel,
        infographic_maker: InfographicMaker

    ):
        self.llm = llm
        self.infographic_maker = infographic_maker

    def run(
        self, 
        prompt: str,         
    ) -> list[Image.Image]:
        html = self.generate_md(prompt)
        style = random.choice(self.infographic_maker.available_styles)
        print("Using style: ", style)
        images = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(self.render, ht, style=style): i for i, ht in enumerate(html.page_contents_markdown)}
            for future in concurrent.futures.as_completed(futures):
                index = futures[future]
                images.append((index, future.result()))
        
        # Sort the images based on their original index and return only the image objects
        return [img for _, img in sorted(images, key=lambda x: x[0])]
    
    def generate_md(self, prompt: str) -> Content:
        structured_llm = self.llm.with_structured_output(Content)
        return structured_llm.invoke(
            [
                SystemMessage(
                    content=f"""You are an AI Teacher. You create fun visualizations to explain various concepts. 
                    Keep them engaging for students.
                    Use emojis to make it look exciting.
                    Deconstruct a topic in bite size chunks. 
                    Keep consistency and break down concepts into pages
                    Make multiple pages (as many as needed) building on the concept.
                    Dont use welcome and conclusion pages.
                    Each page must have atleast 50 characters of content.
                    Remember children will use this we need to explain in simple language and build step by step across pages.
                    Do not use transition pages. (Pages with only topic name to come)
                    """
                ),
                HumanMessage(
                    content=f"Make visuals about '{prompt}'. "
                )
            ]
        )

    def render(self,
        markdown_content: str,
        style: str,
    ) -> Image.Image:
        return self.infographic_maker.make_infographic(markdown=markdown_content, style=style)

if __name__ == "__main__":
    # important settings
    from langchain_openai import ChatOpenAI
    styles = ["card", "card-purple", "student-card", "student-card-2", "student-card-3", "student-card-4", "student-card-5"]
    imgs = ImageExplainers(
        ChatOpenAI(model="gpt-4o-mini", temperature=0),
        InfographicMaker(styles)
    ).run("Water cycle.")
    for i, img in enumerate(imgs):
        img.save(f"img{i}.png")