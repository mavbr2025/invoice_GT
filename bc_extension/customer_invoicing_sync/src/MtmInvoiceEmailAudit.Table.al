table 71011 "MTM Invoice Email Audit"
{
    Caption = 'MTM Invoice Email Audit';
    DataClassification = CustomerContent;

    fields
    {
        field(1; "Posted Invoice System Id"; Guid) { DataClassification = SystemMetadata; }
        field(2; "Posted Invoice No."; Code[20]) { DataClassification = CustomerContent; }
        field(3; "Customer No."; Code[20]) { DataClassification = CustomerContent; }
        field(4; Recipient; Text[250]) { DataClassification = CustomerContent; }
        field(5; "Sender Email"; Text[250]) { DataClassification = CustomerContent; }
        field(6; Status; Option)
        {
            DataClassification = SystemMetadata;
            OptionMembers = Pending,Sent,Failed;
            OptionCaption = 'Pending,Sent,Failed';
        }
        field(7; "Sent At"; DateTime) { DataClassification = SystemMetadata; }
        field(8; "Error Text"; Text[2048]) { DataClassification = CustomerContent; }
        field(9; "Attempt Count"; Integer) { DataClassification = SystemMetadata; }
        field(10; "Report Layout Name"; Text[100]) { DataClassification = SystemMetadata; }
    }

    keys
    {
        key(PK; "Posted Invoice System Id") { Clustered = true; }
        key(InvoiceNo; "Posted Invoice No.") { }
    }
}
