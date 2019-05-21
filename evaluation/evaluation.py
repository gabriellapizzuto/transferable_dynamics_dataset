"""
Evaluation functionality. Note that it can also be called as a script.
"""
import os
import ipdb
import argparse
import numpy as np
from DL.dynamics_learner_interface.dynamics_learner_interface import DynamicsLearnerExample
from DL.utils import Standardizer
from DL.utils.data_loading import loadRobotData


def get_observations_standardizer(testing_observations):
    assert len(testing_observations.shape) == 3
    joint_testing_obs = testing_observations.reshape((-1,
            testing_observations.shape[2]))
    return Standardizer(joint_testing_obs)

def evaluate(dynamics_learner, observation_sequences, action_sequences,
        test_dataset_name):
    possible_history_lengths = [1, 10]
    possible_prediction_horizons = [1, 10, 100, 1000]
    assert dynamics_learner.history_length in possible_history_lengths
    assert dynamics_learner.prediction_horizon in possible_prediction_horizons

    history_length = dynamics_learner.history_length

    # Computing normalization statistics for the observed states in testing set.
    # This way we make sure all the error dimensions have the same scale.
    obs_standardizer = get_observations_standardizer(observation_sequences)

    # Only evaluating in the prediction horizon that a model was trained on.
    prediction_horizons = [dynamics_learner.prediction_horizon]

    output_errors = {}
    for prediction_horizon in prediction_horizons:
        T = range(possible_history_lengths[-1] - 1,
                  observation_sequences.shape[1] - possible_prediction_horizons[-1])
        errors = np.empty((observation_sequences.shape[0],
                           len(T),
                           observation_sequences.shape[2]))
        for i in range(len(T)):
            t = T[i]
            observation_history = observation_sequences[:, t + 1 - history_length: t + 1]
            action_history = action_sequences[:, t + 1 - history_length: t + 1]
            action_future = action_sequences[:, t + 1: t + prediction_horizon]
            observation_prediction = dynamics_learner.predict(
                    observation_history=observation_history,
                    action_history=action_history,
                    action_future=action_future)
            true_observation = observation_sequences[:, t + prediction_horizon]
            errors[:, i] = obs_standardizer.standardize(true_observation) - \
                    obs_standardizer.standardize(observation_prediction)

        errors_key = test_dataset_name + '__history_' + str(history_length) + \
                '__training_horizon_' + \
                str(dynamics_learner.prediction_horizon) + \
                '__evaluation_horizon_' + str(prediction_horizon)
        output_errors[errors_key] = errors
    return output_errors

def compute_RMSE_from_errors(output_errors):
    """
    Computes the RMSE from the error vectors. For now it weights equally
    all the dimensions.
    """
    errors = list(output_errors.values())

    # Right now we only test on the same setup used for training.
    assert len(errors) == 1
    errors = errors[0]
    nseq, length, state_dim = errors.shape
    errors = errors.reshape((-1, state_dim))
    squared_errors = np.sum(errors * errors, axis=1)
    return np.sqrt(np.mean(squared_errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training_data", required=True,
            help="<Required> filename of the input robot training data")
    parser.add_argument("--trained_model",
            help="filename of a trained model. If specified the model won't be"
            " trained")
    parser.add_argument("--testing_data", required=True,
            help="<Required> filename of the input robot testing data")
    parser.add_argument("--method", required=True,
            help="<Required> Name of the method that will be tested")
    parser.add_argument("--history_length", type=int, default=1)
    parser.add_argument("--prediction_horizon", type=int, default=1)
    parser.add_argument("--output_errors", required=True,
            help="<Required> filename where the computed errors will be saved")
    parser.add_argument("--output_model",
            help="filename where the trained model will be saved if a trained"
            " model was not already provided in the command line.")
    args = parser.parse_args()
    history_length = args.history_length
    prediction_horizon = args.prediction_horizon
    dynamics_learner = None
    if args.method == 'example':
        dynamics_learner = DynamicsLearnerExample(1, 1)
    elif args.method == 'pilco_ninducing_500_ntraining_50000':
        from DL.methods.pilco_dynamics_learner import PilcoDynamicsLearner

        ninducing = 500
        ntraining = 50000
        dynamics_learner = PilcoDynamicsLearner(history_length,
                prediction_horizon, ninducing, ntraining)
    elif args.method == 'linear_model_sgd':
        from DL.methods.linear_regression_sgd import LinearModelSGD

        dynamics_learner = LinearModelSGD(1, 1)
    elif args.method == 'BNN':
        from DL.methods.BNN import BNNLearner

        dynamics_learner = BNNLearner(history_length, prediction_horizon)
    assert dynamics_learner, "Make sure the method is implemented."
    training_observations, training_actions = loadRobotData(args.training_data)
    testing_observations, testing_actions = loadRobotData(args.testing_data)
    if args.trained_model:
        dynamics_learner.load_normalization_stats(training_observations,
                training_actions)
        dynamics_learner.load(args.trained_model)
    else:
        dynamics_learner.learn(training_observations, training_actions)
        if args.output_model:
            dynamics_learner.save(args.output_model)
    errors = evaluate(dynamics_learner, testing_observations,
            testing_actions, args.testing_data)
    print(compute_RMSE_from_errors(errors))
    np.savez(args.output_errors, **errors)

