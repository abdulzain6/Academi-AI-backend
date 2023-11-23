import asyncio
import json
from json import JSONDecodeError
from typing import List, Union

from langchain.agents.agent import AgentOutputParser
from langchain.schema import (
    AgentAction,
    AgentFinish,
    OutputParserException,
)
from langchain.schema.agent import AgentActionMessageLog
from langchain.schema.messages import (
    AIMessage,
    BaseMessage,
)
from langchain.schema.output import ChatGeneration, Generation
from langchain.agents.openai_functions_agent.base import OpenAIFunctionsAgent
from langchain.agents.format_scratchpad.openai_functions import (
    format_to_openai_function_messages,
)

class OpenAIFunctionsAgentOutputParser(AgentOutputParser):
    """Parses a message into agent action/finish.

    Is meant to be used with OpenAI models, as it relies on the specific
    function_call parameter from OpenAI to convey what tools to use.

    If a function_call parameter is passed, then that is used to get
    the tool and tool input.

    If one is not passed, then the AIMessage is assumed to be the final output.
    """

    @property
    def _type(self) -> str:
        return "openai-functions-agent"

    @staticmethod
    def _parse_ai_message(message: BaseMessage) -> Union[AgentAction, AgentFinish]:
        """Parse an AI message."""
        if not isinstance(message, AIMessage):
            raise TypeError(f"Expected an AI message got {type(message)}")

        function_call = message.additional_kwargs.get("function_call", {})
        
        if function_call:
            function_name = function_call["name"]
            try:
                if len(function_call["arguments"].strip()) == 0:
                    # OpenAI returns an empty string for functions containing no args
                    _tool_input = {}
                else:
                    # otherwise it returns a json object
                    _tool_input = json.loads(function_call["arguments"])
            except JSONDecodeError:
                _tool_input = {"__arg1" : function_call["arguments"]}


            # HACK HACK HACK:
            # The code that encodes tool input into Open AI uses a special variable
            # name called `__arg1` to handle old style tools that do not expose a
            # schema and expect a single string argument as an input.
            # We unpack the argument here if it exists.
            # Open AI does not support passing in a JSON array as an argument.
            if "__arg1" in _tool_input:
                tool_input = _tool_input["__arg1"]
            else:
                tool_input = _tool_input

            content_msg = f"responded: {message.content}\n" if message.content else "\n"
            log = f"\nInvoking: `{function_name}` with `{tool_input}`\n{content_msg}\n"
            return AgentActionMessageLog(
                tool=function_name,
                tool_input=tool_input,
                log=log,
                message_log=[message],
            )

        return AgentFinish(
            return_values={"output": message.content}, log=str(message.content)
        )

    def parse_result(
        self, result: List[Generation], *, partial: bool = False
    ) -> Union[AgentAction, AgentFinish]:
        if not isinstance(result[0], ChatGeneration):
            raise ValueError("This output parser only works on ChatGeneration output")
        message = result[0].message
        return self._parse_ai_message(message)

    async def aparse_result(
        self, result: List[Generation], *, partial: bool = False
    ) -> Union[AgentAction, AgentFinish]:
        return await asyncio.get_running_loop().run_in_executor(
            None, self.parse_result, result
        )

    def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
        raise ValueError("Can only parse messages")


class ModifiedOpenAIAgent(OpenAIFunctionsAgent):
    def plan(
        self,
        intermediate_steps: List[tuple[AgentAction, str]],
        callbacks = None,
        with_functions: bool = True,
        **kwargs,
    ) -> Union[AgentAction, AgentFinish]:
        """Given input, decided what to do.

        Args:
            intermediate_steps: Steps the LLM has taken to date, along with observations
            **kwargs: User inputs.

        Returns:
            Action specifying what tool to use.
        """
        agent_scratchpad = format_to_openai_function_messages(intermediate_steps)
        selected_inputs = {
            k: kwargs[k] for k in self.prompt.input_variables if k != "agent_scratchpad"
        }
        full_inputs = dict(**selected_inputs, agent_scratchpad=agent_scratchpad)
        prompt = self.prompt.format_prompt(**full_inputs)
        messages = prompt.to_messages()
        if with_functions:
            predicted_message = self.llm.predict_messages(
                messages,
                functions=self.functions,
                callbacks=callbacks,
            )
        else:
            predicted_message = self.llm.predict_messages(
                messages,
                callbacks=callbacks,
            )
        agent_decision = OpenAIFunctionsAgentOutputParser._parse_ai_message(
            predicted_message
        )
        return agent_decision