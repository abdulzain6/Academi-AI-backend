import re
import time
from typing import Dict, List, Optional, Sequence, Tuple, Union
from uuid import UUID
from langchain.agents import Tool
from langchain.agents import AgentExecutor
from pydantic import BaseModel, Field
from .python_exec_client import PythonClient
from langchain.schema import SystemMessage, BaseMessage, HumanMessage, AIMessage, LLMResult
from langchain.callbacks.base import BaseCallbackHandler
from langchain.chat_models.base import BaseChatModel
from langchain.chains import create_extraction_chain
from .modified_openai_agent import ModifiedOpenAIAgent
from typing import Any, Optional, Sequence
from langchain.agents.agent import AgentExecutor
from langchain.callbacks.base import BaseCallbackManager
from langchain.schema.language_model import BaseLanguageModel
from langchain.tools.base import BaseTool
from langchain.schema.agent import AgentFinish


def split_into_chunks(text, chunk_size):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


class CustomCallback(BaseCallbackHandler):
    def __init__(self, callback, on_end_callback) -> None:
        self.callback = callback
        self.on_end_callback = on_end_callback
        super().__init__()
        self.cached = True

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.cached = False
        if not self.cached:
            self.callback(token)
            
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        ...
        self.callback("AI is using a tool to perform calculations to better assist you...\n")
        
    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when tool ends running."""
        self.callback("AI has finished using the tool and will respond shortly...\n")


    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self.on_end_callback(finish.return_values.get("output", ""))
        if self.cached:
            self.callback(finish.return_values.get("output", ""))
        self.callback("@@END@@")


        
class Solution(BaseModel):
    answer_markdown: str = Field(
        None,
        json_schema_extra={
            "description": "The answer to the user question in markdown"
        },
    )
    explanation_markdown: str = Field(
        None,
        json_schema_extra={
            "description": "The explanation for the answer with definitions, assumptions intermediate results, units and problem statement Must explain in the easiest language as possible. Must be in markdown"
        },
    )
    steps: str = Field(
        None,
        json_schema_extra={
            "description": "The step by step methodology used to reach the solution."
        },
    )
    message_user: str = Field(
        None, json_schema_extra={"description": "A useful message to the user."}
    )


class MathSolver:
    def __init__(
        self, python_client: PythonClient, llm_cls: BaseChatModel, llm_kwargs: dict
    ) -> None:
        self.python_client = python_client
        self.llm_cls = llm_cls
        self.llm_kwargs = llm_kwargs

    def make_tools(self) -> list[Tool]:
        try:
            libraries = self.python_client.get_available_libraries()["libraries"]
        except Exception:
            libraries = []

        description = f"""
Used to execute multiline python code wont persist states so run everything once.
Do not pass in Markdown just a normal python string (Important)
Try to run all the code at once
Use tools if you think you need help or to confirm answer. Make sure arguments are loadable by json.loads (Super important) use double quotes or it will cause error
These are the libraries you have access to.
Use print statement to print data.
You will not run unsafe code or perform harm to the server youre on. Or import potentially harmful libraries (Very Important).
Libraries: {libraries}
Do not import libraries that are not allowed.
        """

        def extract_python_code(text: str) -> List[str]:
            """
            Extract Python code blocks from a given text.

            Parameters:
                text (str): The input text containing Python code blocks.

            Returns:
                List[str]: A list of Python code blocks.
            """
            # Regular expression to match Python code blocks enclosed in triple backticks
            pattern = r"```python\n(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL)
            joined_matches = "\n".join(matches)
            return joined_matches or text.strip()

        def python_function(code: str):
            result = self.python_client.evaluate_code(
                extract_python_code(code)
            )
            try:
                return result["result"]
            except Exception as e:
                return result

        return [Tool("python", python_function, description)]

    def make_agent(self, llm: BaseChatModel, chat_history_messages: list[BaseMessage]) -> AgentExecutor:
        agent_kwargs = {
            "system_message": SystemMessage(
                content="""
You are An AI designed to solve mathematical problems and assist students. 
Only pick the tools available (Important)
You will not run unsafe code or perform harm to the server youre on. Or import potentially harmful libraries (Very Important).
Do not import libraries that are not allowed.
You will reject any non math related queries    
Do not return python code to the user.
Explain in detail (Important).
You must return (Important):
    1. The answer to the user question in markdown.
    2. The explanation for the answer with definitions, assumptions intermediate results, units and problem statement Must explain in the easiest language as possible to a non programmer. Must be in markdown
    3. The step by step methodology used to reach the solution.
    4. The steps must be in mathematical notation
A little bit of arthmetic and a logical approach will help us quickly arrive at the solution for this problem
Use tools if you think you need help or to confirm answer.
Make sure arguments to tools are loadable by json.loads (Super important), so use double quotes!! or it will cause error
Reject any non math related queries! (Important)
Use latex for maths equations and symbols (important)
Lets think step by step
"""),
            "extra_prompt_messages" : chat_history_messages
        }
        return self.initialize_agent(
            self.make_tools(),
            llm,
            agent_kwargs=agent_kwargs,
            max_iterations=4,
        )

    def initialize_agent(
        self,
        tools: Sequence[BaseTool],
        llm: BaseLanguageModel,
        callback_manager: Optional[BaseCallbackManager] = None,
        agent_kwargs: Optional[dict] = None,
        **kwargs: Any,
    ):
        agent_obj = ModifiedOpenAIAgent.from_llm_and_tools(
            llm, tools, callback_manager=callback_manager, **agent_kwargs
        )        
        return AgentExecutor.from_agent_and_tools(
            agent=agent_obj,
            tools=tools,
            callback_manager=callback_manager,
            **kwargs,
        )

    def get_structured_output(self, response: str) -> Solution:
        chain = create_extraction_chain(
            Solution.model_json_schema(), self.llm_cls(**self.llm_kwargs)
        )
        return Solution.model_validate(chain.run(response)[0])

    def wrap_prompt(self, prompt: str) -> str:
        return f"""
You are an AI dsigned to help students.
You will use tools to answer questions and reject any unsafe operations like reading files or os related things
lets look at the query and try to answer it 
dont return python code or mention python related stuff. Explain to me as if i was 10 dont mention python functions.. 
Dont mention about tools in your answer just mention the answer
Use latex for maths equations and symbols (important)

Student: {prompt} use tools

A little bit of arthmetic and a logical approach will help us quickly arrive at the solution for this problem, use tools to confirm answer
Answer:"""

    def run_agent(self, prompt: str, structured: bool, stream: bool = False, callback: callable = None, on_end_callback: callable = None, model_name: str = "gpt-3.5-turbo", chat_history: list[tuple[str, str]] = None):
        
        if chat_history is None:
            chat_history = []
            
        if structured and stream:
            raise ValueError("Stream must be disabled for structured output")

        llm = self.llm_cls(**self.llm_kwargs,
            **{"streaming": stream,
                "model_name" : model_name,
        })
        agent = self.make_agent(
            llm=llm,
            chat_history_messages=self.format_messages(chat_history, 700, llm)
        )
        if stream:
            agent = self.make_agent(
                llm=self.llm_cls(**self.llm_kwargs,
                **{"streaming": stream,
                   "model_name" : model_name,
                }),
                chat_history_messages=self.format_messages(chat_history, 700, llm)
            ) 
            if not callback:
                raise ValueError("Callback not passed for streaming to")
            return agent.run(
                self.wrap_prompt(prompt), callbacks=[CustomCallback(callback, on_end_callback)]

            )
        else:
            response = agent.run(self.wrap_prompt(prompt))
            return self.get_structured_output(response) if structured else response

    def format_messages(
        self,
        chat_history: List[Tuple[str, str]],
        tokens_limit: int,
        llm: BaseChatModel,
    ) -> List[BaseMessage]:
        messages: List[BaseMessage] = []
        tokens_used: int = 0

        for human_msg, ai_msg in chat_history:
            human_tokens = llm.get_num_tokens(human_msg)
            ai_tokens = llm.get_num_tokens(ai_msg)

            new_tokens_used = tokens_used + human_tokens + ai_tokens

            if new_tokens_used > tokens_limit:
                break

            tokens_used = new_tokens_used

            messages.extend((HumanMessage(content=human_msg), AIMessage(content=ai_msg)))

        return messages
    
    
