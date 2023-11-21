import logging
import re
import time
from typing import Dict, List, Optional, Sequence, Tuple, Union
from uuid import UUID
from langchain.agents import Tool
from langchain.agents import AgentExecutor
from pydantic import BaseModel, Field
from .python_exec_client import PythonClient
from langchain.schema import (
    SystemMessage,
    BaseMessage,
    HumanMessage,
    AIMessage,
    LLMResult,
)
from langchain.callbacks.base import BaseCallbackHandler
from langchain.chat_models.base import BaseChatModel
from langchain.agents.structured_chat.base import StructuredChatAgent
from langchain.chains import create_extraction_chain
from .modified_openai_agent import ModifiedOpenAIAgent
from typing import Any, Optional, Sequence
from langchain.agents.agent import AgentExecutor
from langchain.callbacks.base import BaseCallbackManager
from langchain.schema.language_model import BaseLanguageModel
from langchain.tools.base import BaseTool
from langchain.schema.agent import AgentFinish
from langchain.agents.openai_functions_agent.base import OpenAIFunctionsAgent



def split_into_chunks(text, chunk_size):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


class CustomCallback(BaseCallbackHandler):
    def __init__(self, callback, on_end_callback, is_openai: bool) -> None:
        self.callback = callback
        self.on_end_callback = on_end_callback
        super().__init__()
        self.cached = True
        self.is_openai = is_openai

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            self.cached = False
        if not self.cached and self.is_openai:
            self.callback(token)

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self.callback(
            "*AI is using a tool to perform calculations to better assist you...*\n"
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when tool ends running."""
        self.callback("\n*AI has finished using the tool and will respond shortly...*\n")

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        print("Agent end", finish, self.cached)
        self.on_end_callback(finish.return_values.get("output", ""))
        if self.cached or not self.is_openai:
            self.callback(finish.return_values.get("output", ""))
        self.callback("@@END@@")
        



class MathSolver:
    def __init__(
        self, python_client: PythonClient, llm: BaseChatModel, is_openai_functions: bool = True, extra_tools: list[Tool] = []
    ) -> None:
        self.python_client = python_client
        self.llm = llm
        self.is_openai_functions = is_openai_functions
        self.python_count = 0
        self.extra_tools = extra_tools

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
            logging.info(f"Runing {code}")
            max_count = 3 if self.is_openai_functions else 2
            if self.python_count >= max_count:
                return "Cannot use tool anymore, just answer what you know"
            result = self.python_client.evaluate_code(extract_python_code(code))
            self.python_count += 1
            try:
                return result["result"]
            except Exception as e:
                return result

        return [Tool("python", python_function, description), *self.extra_tools]

    def make_agent(
        self, llm: BaseChatModel, chat_history_messages: list[BaseMessage]
    ) -> AgentExecutor:
        agent_kwargs = {
            "system_message": SystemMessage(
                content="""
You are An AI designed to solve problems and assist students. 

You must return (Important):
    1. The answer to the user question in markdown.
    2. The explanation for the answer with definitions, assumptions intermediate results, units and problem statement Must explain in the easiest language as possible to a non programmer. Must be in english
    3. The step by step methodology on how the student can solve the exact same question on paper. Keep in mind the student will solve it by hand he has no tools. (Very very important)
    4. The steps must be in english and understandable.
    5. Mathematical steps also if applicable Also return what rules, formulas you use.
    
Rules:
    You will not run unsafe code or perform harm to the server youre on. Or import potentially harmful libraries (Very Important).
    Do not import libraries that are not allowed.
    Do not return python code to the user.(Super important)
    Explain in detail in english (Important).
    The student is solving the question on paper, help him solve on paper he has no tools.
    Use tools if you think you need help or to confirm answer.
    You must use tools to confirm your answer. (Important)
    Use latex for maths equations and symbols (important)
    
Use tools to get accurate answer, dont give approximations (Important)
Always use tools (Important)
Lets think step by step to help the student following all rules. 
"""
            ),
            "extra_prompt_messages": chat_history_messages,
        }
        return self.initialize_agent(
            self.make_tools(),
            llm,
            agent_kwargs=agent_kwargs,
            max_iterations=5,
        )

    def initialize_agent(
        self,
        tools: Sequence[BaseTool],
        llm: BaseLanguageModel,
        callback_manager: Optional[BaseCallbackManager] = None,
        agent_kwargs: Optional[dict] = None,
        **kwargs: Any,
    ):
        if self.is_openai_functions:
            agent_obj = OpenAIFunctionsAgent.from_llm_and_tools(
                llm, tools, callback_manager=callback_manager, **agent_kwargs
            )
        else:
            agent_obj = StructuredChatAgent.from_llm_and_tools(
                llm,
                tools,
                callback_manager=callback_manager,
                prefix=agent_kwargs["system_message"].content,
                memory_prompts=agent_kwargs["extra_prompt_messages"]
            )
        return AgentExecutor.from_agent_and_tools(
            agent=agent_obj,
            tools=tools,
            callback_manager=callback_manager,
            **kwargs,
        )

    def wrap_prompt(self, prompt: str) -> str:
        return f"""{prompt}, [Reminder: Use tools to confirm answer for the user.]"""

    def run_agent(
        self,
        prompt: str,
        callback: callable = None,
        on_end_callback: callable = None,
        chat_history: list[tuple[str, str]] = None,
    ):
        if chat_history is None:
            chat_history = []

        agent = self.make_agent(
            llm=self.llm,
            chat_history_messages=self.format_messages(chat_history, 700, self.llm),
        )
        if not callback:
            raise ValueError("Callback not passed for streaming to")
        
        return agent.run(
            self.wrap_prompt(prompt),
            callbacks=[CustomCallback(callback, on_end_callback, self.is_openai_functions)],
        )

    def format_messages(
        self,
        chat_history: List[Tuple[str, str]],
        tokens_limit: int,
        llm: BaseChatModel,
    ) -> List[BaseMessage]:
        messages: List[BaseMessage] = []
        tokens_used: int = 0

        for human_msg, ai_msg in reversed(chat_history):
            human_tokens = llm.get_num_tokens(human_msg)
            ai_tokens = llm.get_num_tokens(ai_msg)
            if tokens_used + ai_tokens <= tokens_limit:
                messages.append(AIMessage(content=ai_msg))
                tokens_used += ai_tokens

            # Add the human message if it doesn't exceed the limit.
            if tokens_used + human_tokens <= tokens_limit:
                messages.append(HumanMessage(content=human_msg))
                tokens_used += human_tokens
            else:
                break  # If we can't add a human message, we have reached the token limit.

        return list(reversed(messages))
