table 71014 "MTM Manual Inv Email Setup"
{
    Caption = 'MTM Manual Invoice Email Setup';
    DataClassification = SystemMetadata;

    fields
    {
        field(1; "Primary Key"; Code[10])
        {
            Caption = 'Primary Key';
            DataClassification = SystemMetadata;
        }
        field(2; "Capture Enabled"; Boolean)
        {
            Caption = 'Capture Newly Posted Invoices';
            DataClassification = SystemMetadata;
        }
        field(3; "Customer Send Enabled"; Boolean)
        {
            Caption = 'Send Customer Email';
            DataClassification = SystemMetadata;
        }
        field(4; "Poll Interval Minutes"; Integer)
        {
            Caption = 'Poll Interval (Minutes)';
            DataClassification = SystemMetadata;
            InitValue = 2;

            trigger OnValidate()
            begin
                if "Poll Interval Minutes" < 1 then
                    Error('Poll Interval Minutes must be at least 1.');
            end;
        }
        field(5; "Stamp Wait Timeout Minutes"; Integer)
        {
            Caption = 'Stamp Wait Timeout (Minutes)';
            DataClassification = SystemMetadata;
            InitValue = 120;

            trigger OnValidate()
            begin
                if "Stamp Wait Timeout Minutes" < 5 then
                    Error('Stamp Wait Timeout Minutes must be at least 5.');
            end;
        }
        field(6; "Initial Delay Seconds"; Integer)
        {
            Caption = 'Initial Delay (Seconds)';
            DataClassification = SystemMetadata;
            InitValue = 60;

            trigger OnValidate()
            begin
                if "Initial Delay Seconds" < 15 then
                    Error('Initial Delay Seconds must be at least 15.');
            end;
        }
        field(7; "Maximum Entries Per Run"; Integer)
        {
            Caption = 'Maximum Entries Per Run';
            DataClassification = SystemMetadata;
            InitValue = 25;

            trigger OnValidate()
            begin
                if ("Maximum Entries Per Run" < 1) or ("Maximum Entries Per Run" > 100) then
                    Error('Maximum Entries Per Run must be between 1 and 100.');
            end;
        }
        field(8; "Last Activated At"; DateTime)
        {
            Caption = 'Last Activated At';
            DataClassification = SystemMetadata;
        }
        field(9; "Last Activated By"; Text[100])
        {
            Caption = 'Last Activated By';
            DataClassification = EndUserIdentifiableInformation;
        }
    }

    keys
    {
        key(PK; "Primary Key") { Clustered = true; }
    }
}
