from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

PROMPT_TEXT = """You are a test engineer working on creating test data for a new feature. You are given a variable "{name}" with some associated constraints.

First, explain the meaning of each constraint. Then think step by step to find a string value for "{name}" that satisfy ALL following constraints:
{constraints}
If the word "{name}" is meaningful, the value should be as realistic for "{name}" as possible.

The output should follow the following format. If no value can satisfy all constraints, assign the value "UNSAT":
{output_format}

Keep the results concise. If the answer is not correct, then you will be fired from your job.
"""  # noqa: E501


class Result(BaseModel):
    value: str = Field(description="The string value that satisfies the constraints.")


def get_prompt(parser: PydanticOutputParser) -> PromptTemplate:
    return PromptTemplate(
        template=PROMPT_TEXT,
        input_variables=["name", "constraints"],
        partial_variables={"output_format": parser.get_format_instructions()},
    )
