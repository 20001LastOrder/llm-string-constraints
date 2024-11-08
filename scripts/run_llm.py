import os
from argparse import ArgumentParser

import pandas
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from tqdm import tqdm

from constraints import ConstraintStore
from llm_string.prompt import Result, get_prompt
from llm_string.utils import JSONPydanticOutputParser
from langchain_ollama import ChatOllama

from z3 import Solver, sat


def call_llm(
    name: str, constraints: list[str], chain: Runnable, parser: JSONPydanticOutputParser
) -> Result:
    constraints = "\n".join(constraints)
    while True:
        result = chain.invoke(input={"name": name, "constraints": constraints})
        try:
            return parser.parse(result.content)
        except ValueError:
            continue


def evaluate_constraints_llm(
    name: str,
    results: list[dict],
    chain: Runnable,
    constraint_store: ConstraintStore,
    parser: JSONPydanticOutputParser,
    args,
):
    num_constraint = constraint_store.get_num_constraints(name)
    truth_masks = [True for _ in range(num_constraint)]

    # get the full positive constraints
    constraints = constraint_store.get_nl_constraints(name, truth_masks)
    if args.use_variable_name:
        result = call_llm(name, constraints, chain, parser)
    else:
        constraints = [
            constraint.replace(name.lower(), "x") for constraint in constraints
        ]
        result = call_llm("x", constraints, chain, parser)
    results.append(
        {"name": name, "result": result.value, "truth_masks": truth_masks.copy()}
    )

    # get the (partially) negative constraints
    for i in tqdm(range(num_constraint), desc=f"Evaluating {name}"):
        truth_masks[i] = False
        constraints = constraint_store.get_nl_constraints(name, truth_masks)
        result = call_llm(name, constraints, chain, parser)
        results.append(
            {"name": name, "result": result.value, "truth_masks": truth_masks.copy()}
        )
        truth_masks[i] = True


def call_smt(constraints: list[str]) -> Result:

    solver = Solver()
    problem = ["(declare-const s String)"] + constraints
    cons_str = "\n".join(problem)
    solver.from_string(cons_str)

    # call the solver
    sat_res = solver.check()
    if sat_res == sat:
        model = solver.model()
        str_val = model[model.decls()[0]]
        # str_val = str_val.as_string() # NOTE this is taking long for some reason
        # str_val = str_val.strip('"')
    else:
        str_val = None

    return sat_res, str_val


def evaluate_constraints_smt(
    name: str,
    results: list[dict],
    constraint_store: ConstraintStore,
):
    # TODO integrate other SMT solvers (maybe)
    num_constraint = constraint_store.get_num_constraints(name)
    truth_masks = [True for _ in range(num_constraint)]

    # get the full positive constraints
    constraints = constraint_store.get_smt_constraints(name, truth_masks)
    sat_res, str_val = call_smt(constraints)

    results.append(
        {
            "name": name,
            "sat": sat_res,
            "result": str_val,
            "truth_masks": truth_masks.copy(),
        }
    )

    # get the (partially) negative constraints
    for i in tqdm(range(num_constraint), desc=f"Evaluating {name}"):
        truth_masks[i] = False

        constraints = constraint_store.get_smt_constraints(name, truth_masks)
        sat_res, str_val = call_smt(constraints)
        results.append(
            {
                "name": name,
                "sat": sat_res,
                "result": str_val,
                "truth_masks": truth_masks.copy(),
            }
        )
        truth_masks[i] = True


def main(args):

    constraint_store = ConstraintStore(file_path=args.file_path)
    names = constraint_store.get_constraint_names()
    results = []

    if args.approach == "llm":
        llm = (
            ChatOpenAI(model=args.llm)
            if args.llm_family == "openai"
            else ChatOllama(model=args.llm, max_new_tokens=500)
        )

        parser = JSONPydanticOutputParser(pydantic_object=Result)
        prompt = get_prompt(parser)

        chain = prompt | llm

    for name in tqdm(names, desc="Evaluating all constraints"):
        if args.approach == "llm":
            evaluate_constraints_llm(
                name, results, chain, constraint_store, parser, args
            )
        else:
            evaluate_constraints_smt(name, results, constraint_store)

    # Set save path
    if args.approach == "smt":
        save_path = os.path.join(args.output_path, f"{args.smt_solver}.csv")
    elif args.use_variable_name:
        save_path = os.path.join(args.output_path, f"{args.llm.replace(':', '-')}.csv")
    else:
        save_path = os.path.join(args.output_path, f"{args.llm.replace(':', '-')}_no_name.csv")

    # Save CSV
    df = pandas.DataFrame(results)
    print(df)
    df.to_csv(save_path, index=False)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--approach", type=str, choices=["llm", "smt"], required=True)
    parser.add_argument("--file_path", type=str, required=True)
    parser.add_argument("--output_path", type=str, required=True)
    parser.add_argument("--llm_family", type=str, default="openai")
    parser.add_argument("--llm", type=str)
    parser.add_argument("--use_variable_name", action="store_true")
    parser.add_argument("--smt_solver", type=str, choices=["z3"])

    args = parser.parse_args()
    main(args)