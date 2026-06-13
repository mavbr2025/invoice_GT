page 71007 "MTM Posted Inv FEL Desc API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'invoiceSync';
    APIVersion = 'v1.0';
    EntityName = 'postedInvoiceFelDescription';
    EntitySetName = 'postedInvoiceFelDescriptions';
    SourceTable = "Sales Invoice Header";
    ODataKeyFields = SystemId;
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    Permissions =
        tabledata "Sales Invoice Header" = rm,
        tabledata "Sales Invoice Line" = rm;

    layout
    {
        area(Content)
        {
            repeater(General)
            {
                field(id; Rec.SystemId)
                {
                    Caption = 'Id';
                    Editable = false;
                }
                field(number; Rec."No.")
                {
                    Caption = 'Number';
                    Editable = false;
                }
                field(customerNumber; Rec."Sell-to Customer No.")
                {
                    Caption = 'Customer Number';
                    Editable = false;
                }
                field(externalDocumentNumber; Rec."External Document No.")
                {
                    Caption = 'External Document Number';
                    Editable = false;
                }
                field(systemModifiedAt; Rec.SystemModifiedAt)
                {
                    Caption = 'System Modified At';
                    Editable = false;
                }
                field(electronicDocumentStatus; GetDynamicFieldText('Electronic Document Status'))
                {
                    Caption = 'Electronic Document Status';
                    Editable = false;
                }
                field(fiscalInvoiceNumberPac; GetDynamicFieldText('Fiscal Invoice Number PAC'))
                {
                    Caption = 'Fiscal Invoice Number PAC';
                    Editable = false;
                }
                field(dateTimeStamped; GetDynamicFieldText('Date/Time Stamped'))
                {
                    Caption = 'Date/Time Stamped';
                    Editable = false;
                }
                field(dateTimeCanceled; GetDynamicFieldText('Date/Time Canceled'))
                {
                    Caption = 'Date/Time Canceled';
                    Editable = false;
                }
                field(errorDescription; GetDynamicFieldText('Error Description'))
                {
                    Caption = 'Error Description';
                    Editable = false;
                }
                field(cancelled; Rec.Cancelled)
                {
                    Caption = 'Cancelled';
                    Editable = false;
                }
                field(cfdiCancellationId; GetDynamicFieldText('CFDI Cancellation ID'))
                {
                    Caption = 'CFDI Cancellation ID';
                    Editable = false;
                }
                field(cfdiCancellationReasonCode; GetDynamicFieldText('CFDI Cancellation Reason Code'))
                {
                    Caption = 'CFDI Cancellation Reason Code';
                    Editable = false;
                }
                field(cancelGtUuid; Rec.CancelaGTUUID)
                {
                    Caption = 'Cancel GT UUID';
                    Editable = false;
                }
            }
        }
    }

    [ServiceEnabled]
    procedure SyncFelLineDescriptions(var ActionContext: WebServiceActionContext)
    var
        CustomerInvoicingMgt: Codeunit "MTM Customer Invoicing Mgt";
    begin
        CustomerInvoicingMgt.SyncPostedInvoiceLineDescriptions(Rec."No.");

        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"MTM Posted Inv FEL Desc API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;

    [ServiceEnabled]
    procedure StampFelInvoice(var ActionContext: WebServiceActionContext)
    var
        GTFelMgt: Codeunit "MTM GT Posted Inv FEL Mgt";
    begin
        GTFelMgt.StampPostedInvoiceNoEmail(Rec);

        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"MTM Posted Inv FEL Desc API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;

    [ServiceEnabled]
    procedure SendFelInvoice(var ActionContext: WebServiceActionContext)
    begin
        Error('LEGACY FEL CUSTOMER SEND IS DISABLED. USE STAMPFELINVOICE FOR SAT/FEL STAMPING, THEN DELIVER THE BUSINESS CENTRAL SALESINVOICES PDFDOCUMENT ATTACHMENT.');
    end;

    [ServiceEnabled]
    procedure ProcessFelInvoiceResponse(var ActionContext: WebServiceActionContext)
    var
        GTMLeerDocumentos: Codeunit GTMLeerDocumentos;
    begin
        GTMLeerDocumentos.ExtractXMLData('Factura');

        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"MTM Posted Inv FEL Desc API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;

    [ServiceEnabled]
    procedure CancelFelInvoice(var ActionContext: WebServiceActionContext)
    var
        FunFacturaGT: Codeunit "Fun. Factura GT";
    begin
        FunFacturaGT.CancelaFacturaGT(Rec);

        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"MTM Posted Inv FEL Desc API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;

    [ServiceEnabled]
    procedure CancelFelInvoiceWithReason(cancellationReasonId: Text; var ActionContext: WebServiceActionContext)
    var
        FunFacturaGT: Codeunit "Fun. Factura GT";
    begin
        SetDynamicFieldText('CFDI Cancellation ID', cancellationReasonId);
        FunFacturaGT.CancelaFacturaGT(Rec);

        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"MTM Posted Inv FEL Desc API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;

    [ServiceEnabled]
    procedure CancelFelInvoiceWithMotive(motiveText: Text; var ActionContext: WebServiceActionContext)
    var
        GTFelMgt: Codeunit "MTM GT Posted Inv FEL Mgt";
    begin
        GTFelMgt.CancelPostedInvoiceWithMotive(Rec, motiveText);

        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"MTM Posted Inv FEL Desc API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;

    [ServiceEnabled]
    procedure CancelPostedInvoiceAndFelWithMotive(motiveText: Text; var ActionContext: WebServiceActionContext)
    var
        CorrectPostedSalesInvoice: Codeunit "Correct Posted Sales Invoice";
        GTFelMgt: Codeunit "MTM GT Posted Inv FEL Mgt";
    begin
        if not Rec.Cancelled then begin
            CorrectPostedSalesInvoice.CancelPostedInvoice(Rec);
            Rec.Get(Rec."No.");
        end;

        GTFelMgt.CancelPostedInvoiceWithMotive(Rec, motiveText);

        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"MTM Posted Inv FEL Desc API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;

    local procedure GetDynamicFieldText(FieldName: Text): Text
    var
        RecRef: RecordRef;
        FieldRef: FieldRef;
    begin
        RecRef.GetTable(Rec);
        if not TryGetFieldByName(RecRef, FieldName, FieldRef) then
            exit('');

        exit(Format(FieldRef.Value()));
    end;

    local procedure SetDynamicFieldText(FieldName: Text; FieldValue: Text)
    var
        RecRef: RecordRef;
        FieldRef: FieldRef;
    begin
        RecRef.GetTable(Rec);
        TryGetFieldByName(RecRef, FieldName, FieldRef);
        FieldRef.Value(FieldValue);
        RecRef.Modify();
        Rec.Get(Rec."No.");
    end;

    [TryFunction]
    local procedure TryGetFieldByName(var RecRef: RecordRef; FieldName: Text; var FieldRef: FieldRef)
    var
        FieldNo: Integer;
    begin
        for FieldNo := 1 to RecRef.FieldCount() do begin
            FieldRef := RecRef.FieldIndex(FieldNo);
            if FieldRef.Name() = FieldName then
                exit;
        end;

        Error('Field %1 was not found.', FieldName);
    end;
}
