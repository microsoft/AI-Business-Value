let
    // One fixed endpoint per Lakehouse; table and schema names are navigation only.
    BasePath = "https://onelake.dfs.fabric.microsoft.com/"
        & #"Fabric Workspace ID" & "/" & #"Lakehouse ID" & "/Tables",
    Tables = AzureStorage.DataLake(BasePath, [HierarchicalNavigation = true]),
    ReadTable = (tableName as text) as table =>
        let
            Lower = Text.Lower(tableName),
            Folders = Table.SelectRows(Tables, each Value.Is([Content], type table)),
            Direct = Table.SelectRows(Folders, each Text.Lower([Name]) = Lower),
            Nested = List.Transform(Table.ToRecords(Folders), (folder) =>
                Table.SelectRows(folder[Content],
                    each Text.Lower([Name]) = Lower and Value.Is([Content], type table))),
            Matches = Table.Combine({Direct} & Nested),
            Count = Table.RowCount(Matches),
            Directory =
                if Count = 1 then Matches{0}[Content]
                else if Count = 0 then error Error.Record("OneLake.TableNotFound",
                    "Table '" & tableName & "' was not found under Lakehouse Tables.", tableName)
                else error Error.Record("OneLake.AmbiguousTable",
                    "Table '" & tableName & "' exists in more than one location. Use a unique table name.", tableName),
            Data = DeltaLake.Table(Directory)
        in
            Data
in
    ReadTable
