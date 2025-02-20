import argparse
import pandas as pd
from pathlib import Path
import logging
from sklearn.model_selection import train_test_split, StratifiedKFold
import numpy as np

class DataPreprocessor:
    def __init__(
        self,
        output_path: Path = Path("data/processed"),
        remove_outliers: bool = False,
        fillna: bool = False,
        use_dummies: bool = False,
        save_as_pickle: bool = True,
        catb: bool = True,
        use_missing_with_mode: bool = False,
        fill_cat: bool = False,

        callback=None
    ):
        self.output_path = output_path
        self.remove_outliers = remove_outliers
        self.catb = catb
        self.fillna = fillna
        self.use_dummies = use_dummies
        self.use_missing_with_mode = use_missing_with_mode
        self.save_as_pickle = save_as_pickle
        self.callback = callback or (lambda x: None)  # Default no-op callback if none provided
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.fill_cat = fill_cat
        

        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    ########################################################################################################################################################
    
    """       
    ╦ ╦┌─┐┬  ┌─┐┌─┐┬─┐  ╔═╗┬ ┬┌┐┌┌─┐┌┬┐┬┌─┐┌┐┌┌─┐
    ╠═╣├┤ │  ├─┘├┤ ├┬┘  ╠╣ │ │││││   │ ││ ││││└─┐
    ╩ ╩└─┘┴─┘┴  └─┘┴└─  ╚  └─┘┘└┘└─┘ ┴ ┴└─┘┘└┘└─┘

    """

    def load_data(self, csv_path: Path) -> pd.DataFrame:
        if not csv_path.exists():
            raise FileNotFoundError(f"File not found: {csv_path}")
        df = pd.read_csv(csv_path)
        X_test_external = pd.read_csv("data/raw/X_test_1st.csv")
        
        self.logger.info(f"Loading file from: {csv_path}")
        return df, X_test_external
    
    def remove_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        if "age_level" in df.columns:
            mean = df["age_level"].mean()
            std = df["age_level"].std()
            outlier_condition = (
                (df["age_level"] > mean + 3 * std) |
                (df["age_level"] < mean - 3 * std)
            )
            num_outliers = outlier_condition.sum()
            df = df[~outlier_condition]
            self.logger.info(f"Removed {num_outliers} outliers based on age_level")
            
        return df
    
    def ffill_bfill_target(self, df, columns, group_by_col="user_id"): # Change to mode, change rows with fault user_id filling
        df_temp = df.copy()
        if "DateTime" in df.columns:
            df_temp = df_temp.sort_values("DateTime")
        result = (
            df_temp.groupby(group_by_col, observed=True)[columns]
            .transform(lambda x: x.ffill().bfill())
            .infer_objects(copy=False)
        )
        result = result.sample(frac=1)  # Shuffle rows

        return result

    def mode_target(self, df, columns, group_by_col="user_id"):
        df_temp = df.copy()
        result = pd.DataFrame(index=df_temp.index)
        
        for column in columns:
            mode = df_temp.groupby(group_by_col, observed=True)[column].transform(lambda x: x.mode().iloc[0] if not x.mode().empty else np.nan)
            result[column] = mode
        
        result = result.sample(frac=1)  # Shuffle rows
        return result
    
    def fill_with_mode(self,df, columns): 
        for column in columns:
            if column in df.columns:
                mode_value = df[column].mode()
                if not mode_value.empty:
                    df[column] = df[column].fillna(mode_value.iloc[0])
        return df

    def _fill_with_median(self,df, columns): # Maybe groupby user_id
        for column in columns:
            if column in df.columns:
                median_value = df[column].median()
                df[column] = df[column].fillna(median_value)
        return df
    
    def determine_categorical_features(self, df: pd.DataFrame, cat_features: list = None): ## For catboost
        """
        Identify and process categorical features, ensuring compatibility with CatBoost.
        """
        cat_cols = ["product_category", "product", "gender", "campaign_id", "webpage_id", "user_group_id"]
        for col in cat_cols:
            if col in df.columns:
                if col in ["campaign_id", "webpage_id", "user_group_id", "product_category"]:
                    df[col] = df[col].astype("Int64").astype("category")
                else:
                    df[col] = df[col].astype("category")
        if cat_features:
            cat_features = [col for col in cat_features if col in df.columns]
        else:
            cat_features = df.select_dtypes(include=['object', 'category']).columns.tolist()

        for col in cat_features:
            if col in df.columns:

                # Add "missing" only if it's not already a category
                if "missing" not in df[col].cat.categories:
                    df[col] = df[col].cat.add_categories("missing")

                # Fill missing values with "missing"
                df[col] = df[col].fillna("missing")

        return cat_features
    
    ########################################################################################################################################################

    """
    ╔═╗┬┬  ┬    ╔╦╗┬┌─┐┌─┐┬┌┐┌┌─┐  ╦  ╦┌─┐┬  ┬ ┬┌─┐┌─┐
    ╠╣ ││  │    ║║║│└─┐└─┐│││││ ┬  ╚╗╔╝├─┤│  │ │├┤ └─┐
    ╚  ┴┴─┘┴─┘  ╩ ╩┴└─┘└─┘┴┘└┘└─┘   ╚╝ ┴ ┴┴─┘└─┘└─┘└─┘

    """

    def fill_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Fill missing values using mode, median, or forward/backward fill.
        Includes subfunctions for modularity.
        """
        df = df.copy()
        self.logger.info(f"NAs in the dataset: {df.isna().sum().sum()}")
        df["user_id"] = df["user_id"].fillna(-1).astype("int32")        
        df["product_category"] = df["product_category_1"].fillna(df["product_category_2"])
        df.drop(columns=["product_category_1", "product_category_2"], inplace=True)


        # Apply mode-based filling if enabled
        if self.fill_cat:
            cat_cols_to_fill = ["product", "campaign_id", "webpage_id", "gender", "product_category", "user_group_id"]
            df = self.mode_target(df, cat_cols_to_fill, "user_id")

        cols_for_ffill_bfill = ["age_level", "city_development_index","var_1", "user_depth"]
        self.logger.info(f"Filling missing values with user_id for columns: {cols_for_ffill_bfill}")
        self.logger.info(f'Number of missing values before: {df[cols_for_ffill_bfill].isna().sum()}')
        df[cols_for_ffill_bfill] = self.mode_target(df, cols_for_ffill_bfill,"user_id")
        self.logger.info(f'Number of missing values after: {df[cols_for_ffill_bfill].isna().sum()}')

        if df[cols_for_ffill_bfill].isna().sum().sum() > 0:
            self.logger.warning(f'Still missing values in columns: {cols_for_ffill_bfill}')
            self.logger.info(f"Filling missing values with user_group_id for columns: {cols_for_ffill_bfill}")
            for col in cols_for_ffill_bfill:
                mask = df[col].isna()  # Identify rows where the value is still missing
                if mask.sum() > 0:
                    df.loc[mask, col] = self.mode_target(df, [col], "user_group_id").loc[mask, col]
            self.logger.info(f'Number of missing values after: {df[cols_for_ffill_bfill].isna().sum()}')

            if df[cols_for_ffill_bfill].isna().sum().sum() > 0:
                self.logger.warning(f'Still missing values in columns: {cols_for_ffill_bfill}')
                self.logger.info(f"Filling missing values with mode for columns: {cols_for_ffill_bfill}")
                df = self.fill_with_mode(df, cols_for_ffill_bfill)
                self.logger.info(f'Number of missing values after: {df[cols_for_ffill_bfill].isna().sum()}')
        if "is_click" in df.columns:
            missing_is_click = df["is_click"].isna().sum()
            if missing_is_click > 0:
                self.logger.warning(f"{missing_is_click} rows still have missing 'is_click'. Dropping these rows.")
                df = df.dropna(subset=["is_click"])

        
        return df

    ########################################################################################################################################################
    
    """
    ╔═╗┌─┐┌─┐┌┬┐┬ ┬┬─┐┌─┐  ╔═╗┌─┐┌┐┌┌─┐┬─┐┌─┐┌┬┐┬┌─┐┌┐┌
    ╠╣ ├┤ ├─┤ │ │ │├┬┘├┤   ║ ╦├┤ │││├┤ ├┬┘├─┤ │ ││ ││││
    ╚  └─┘┴ ┴ ┴ └─┘┴└─└─┘  ╚═╝└─┘┘└┘└─┘┴└─┴ ┴ ┴ ┴└─┘┘└┘

    """
    def feature_generation(self, df: pd.DataFrame):
        df = df.copy()

        # Generate time-based features
        df['Day'] = df['DateTime'].dt.day
        df['Hour'] = df['DateTime'].dt.hour
        df['Minute'] = df['DateTime'].dt.minute
        df['weekday'] = df['DateTime'].dt.weekday

        cols_to_fill = ["Day", "Hour", "Minute", "weekday"]   
        self.logger.info(f"Filling missing values with user_id for columns: {cols_to_fill}")
        df[cols_to_fill] = self.mode_target(df, cols_to_fill,"user_id")
        #(df.groupby("user_id",observed = True)[cols_to_fill]
        #    .transform(lambda x: x.ffill().bfill())
        #    .infer_objects(copy=False)
        #)
        colls_to_fill_nas = df[cols_to_fill].isna().sum()
        if colls_to_fill_nas.sum() > 0:
            self.logger.warning(f"Still missing values in columns: {colls_to_fill_nas.sum()}")
            df[cols_to_fill] = df[cols_to_fill].fillna(df[cols_to_fill].mode().iloc[0])
        self.logger.info("Filled missing values with forward/backward fill.")
        # Fill missing values
        if self.use_missing_with_mode:
            df = self.fill_missing_values(df, use_mode=True)

        # Generate campaign-based features
        df['start_date'] = df.groupby('campaign_id', observed=True)['DateTime'].transform('min')
        df['campaign_duration'] = df['DateTime'] - df['start_date']
        df['campaign_duration_hours'] = df['campaign_duration'].dt.total_seconds() / (3600)
        df['campaign_duration_hours'] = df['campaign_duration_hours'].fillna(
            df.groupby('campaign_id', observed=True)['campaign_duration_hours'].transform(lambda x: x.mode().iloc[0])
            )
        df['campaign_duration_hours'] = pd.to_numeric(df['campaign_duration_hours'], errors='coerce')
        self.logger.info(f'missing values in campaign_duration_hours: {df["campaign_duration_hours"].isna().sum()}')
        

        # Drop unnecessary columns
        df.drop(columns=['DateTime', 'start_date', 'campaign_duration', 'session_id', 'user_id'], inplace=True)
      
        if self.catb:
            self.determine_categorical_features(df)
        # One-hot encoding if `get_dumm` is True
        df['campaign_duration_hours'] = df.groupby('webpage_id', observed=True)['campaign_duration_hours'].transform(
            lambda x: x.ffill().bfill() if not x.mode().empty else x.fillna(0))
        

        self.logger.info(f'missing values in campaign_duration_hours after: {df["campaign_duration_hours"].isna().sum()}')

        if self.use_dummies:
            columns_to_d = ["product", "campaign_id", "webpage_id", "product_category", "gender"]
            df = pd.get_dummies(df, columns=columns_to_d)

        return df
    
    ########################################################################################################################################################
    
    """
    ╔═╗┬─┐┌─┐┌─┐┬─┐┌─┐┌─┐┌─┐┌─┐┌─┐
    ╠═╝├┬┘├┤ ├─┘├┬┘│ ││  ├┤ └─┐└─┐
    ╩  ┴└─└─┘┴  ┴└─└─┘└─┘└─┘└─┘└─┘

    """
    
    def preprocess(self, df: pd.DataFrame, X_test_1st) -> tuple:
        #df_clean = df.drop_duplicates().copy()
        df_clean = df[~df['session_id'].duplicated(keep='first') | df['session_id'].isna()].copy()
        X_test_1st = X_test_1st[~X_test_1st['session_id'].duplicated(keep='first') | X_test_1st['session_id'].isna()].copy()
        self.logger.info(f"Initial shape: {df.shape}. After removing duplicates: {df_clean.shape}")

        if "DateTime" in df_clean.columns:
            df_clean["DateTime"] = pd.to_datetime(df_clean["DateTime"], errors="coerce")
            X_test_1st["DateTime"] = pd.to_datetime(X_test_1st["DateTime"], errors="coerce")

        if self.remove_outliers:
            df_clean = self.remove_outliers(df_clean)
            X_test_1st = self.remove_outliers(X_test_1st)

        if self.fillna:
            df_clean = self.fill_missing_values(df_clean)
            X_test_1st = self.fill_missing_values(X_test_1st)

        df_clean = self.feature_generation(df_clean)
        X_test_1st = self.feature_generation(X_test_1st)

        X = df_clean.drop(columns=["is_click"])
        y = df_clean["is_click"]

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # Create stratified folds for train set
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        fold_datasets = []

        for fold, (train_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
            X_train_fold = X_train.iloc[train_idx]
            y_train_fold = y_train.iloc[train_idx]
            X_val_fold = X_train.iloc[val_idx]
            y_val_fold = y_train.iloc[val_idx]
            fold_datasets.append((X_train_fold, y_train_fold, X_val_fold, y_val_fold))
            self.callback({
            f"fold_{fold}_train_dataset": X_train_fold,
            f"fold_{fold}_val_dataset": X_val_fold,
            f"fold_{fold}_train_target": y_train_fold,
            f"fold_{fold}_val_target": y_val_fold
            })
        self.callback({
            "X_train": X_train,
            "X_test": X_test,
            "y_train": y_train,
            "y_test": y_test
        })
        self.logger.info("Created stratified folds for training data.")

        return df_clean, X_train, X_test, y_train, y_test, fold_datasets, X_test_1st
    
    r"""
     ____                  
    / ___|  __ ___   _____ 
    \___ \ / _` | \ / / _ |
     ___) | (_| |\ V /  __/
    |____/ \__,_| \_/ \___|
                        
    """

    def save_data(self, df_clean, X_train, X_test, y_train, y_test, fold_datasets, X_test_1st):
        if self.save_as_pickle:
            df_clean.to_pickle(self.output_path / "cleaned_data.pkl")
            X_train.to_pickle(self.output_path / "X_train.pkl")
            X_test.to_pickle(self.output_path / "X_test.pkl")
            y_train.to_pickle(self.output_path / "y_train.pkl")
            y_test.to_pickle(self.output_path / "y_test.pkl")
            X_test_1st.to_pickle(self.output_path / "X_test_DoNotTouch.pkl")
            
            # Save folds
            for i, (X_train_fold, y_train_fold, X_val_fold, y_val_fold) in enumerate(fold_datasets):
                X_train_fold.to_pickle(self.output_path / f"X_train_fold_{i}.pkl")
                y_train_fold.to_pickle(self.output_path / f"y_train_fold_{i}.pkl")
                X_val_fold.to_pickle(self.output_path / f"X_val_fold_{i}.pkl")
                y_val_fold.to_pickle(self.output_path / f"y_val_fold_{i}.pkl")

            self.logger.info(f"Saved preprocessed data, train-test split, and folds as Pickle to {self.output_path}")
        else:
            df_clean.to_csv(self.output_path / "cleaned_data.csv", index=False)
            X_train.to_csv(self.output_path / "X_train.csv", index=False)
            X_test.to_csv(self.output_path / "X_test.csv", index=False)
            y_train.to_csv(self.output_path / "y_train.csv", index=False, header=True)
            y_test.to_csv(self.output_path / "y_test.csv", index=False, header=True)
            X_test_1st.to_csv(self.output_path / "X_test_DoNotTouch.csv", index=False)
            
            # Save folds
            for i, (X_train_fold, y_train_fold, X_val_fold, y_val_fold) in enumerate(fold_datasets):
                X_train_fold.to_csv(self.output_path / f"X_train_fold_{i}.csv", index=False)
                y_train_fold.to_csv(self.output_path / f"y_train_fold_{i}.csv", index=False, header=True)
                X_val_fold.to_csv(self.output_path / f"X_val_fold_{i}.csv", index=False)
                y_val_fold.to_csv(self.output_path / f"y_val_fold_{i}.csv", index=False, header=True)

            self.logger.info(f"Saved preprocessed data, train-test split, and folds as CSV to {self.output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv_path", type=str, default="data/raw/train_dataset_full.csv", help="Path to the input CSV file")
    parser.add_argument("--output_path", type=str, default="data/processed", help="Path to save the output data")
    parser.add_argument("--remove-outliers", action="store_true", help="Flag to remove outliers")
    parser.add_argument("--fillna", action="store_true", help="Flag to fill missing values")
    parser.add_argument("--use-dummies", action="store_true", help="Flag to apply pd.get_dummies")
    parser.add_argument("--use-missing-with-mode", action="store_true", help="Flag to fill missing values with mode")
    parser.add_argument("--save-as-pickle", action="store_true", default=True, help="Flag to save as Pickle instead of CSV")
    parser.add_argument("--fill-cat", action="store_true", help="Flag to fill categorical columns")
    args = parser.parse_args()

    preprocessor = DataPreprocessor(
        output_path=Path(args.output_path),
        remove_outliers=args.remove_outliers,
        fillna=args.fillna,
        use_dummies=args.use_dummies,
        save_as_pickle=args.save_as_pickle
    )

    df,X_test_1st = preprocessor.load_data(Path(args.csv_path))
    df_clean, X_train, X_test, y_train, y_test, fold_datasets,X_test_1st = preprocessor.preprocess(df,X_test_1st)
    preprocessor.save_data(df_clean, X_train, X_test, y_train, y_test, fold_datasets,X_test_1st)
